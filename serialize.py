#!/usr/bin/env python

from __future__ import print_function

import os
from subprocess import PIPE, Popen
import sys
from time import sleep

import backoff
from boto.dynamodb2 import connect_to_region
from boto.dynamodb2.exceptions import ConditionalCheckFailedException, \
		ItemNotFound, ProvisionedThroughputExceededException
from boto.dynamodb2.fields import HashKey
from boto.dynamodb2.items import Item
from boto.dynamodb2.table import Table
from boto.exception import JSONResponseError


TABLE = 'serialize-ansible'
THROUGHPUT = {'read':1, 'write': 1}


def serialize(project, playbook):
	table = get_table()
	state = get_state(table, project)

	if state['state'] == 'blocked':
		print('Project "%s" is blocked' % project, file=sys.stderr)
		return
	if playbook in state.get('waiting', set()):
		print('Project "%s" playbook "%s" is already waiting' %
				(project, playbook), file=sys.stderr)
		return

	mark_waiting(state, playbook)
	try:
		wait_and_activate(state)
	finally:
		unmark_waiting(state, playbook)

	try:
		return run_playbook(playbook)
	finally:
		deactivate(state)


def get_table():
	table_props = {
		'table_name': TABLE,
		'schema': [HashKey('project')],
		'throughput': THROUGHPUT,
	}
	table = Table(**table_props)
	while True:
		try:
			desc = describe_table(table)
			status = desc['Table']['TableStatus']
			if status != 'CREATING':
				break
			sleep(1)
		except JSONResponseError, e:
			if e.error_code == 'ResourceNotFoundException':
				table = Table.create(**table_props)
			else:
				raise e
	if status != 'ACTIVE':
		raise Exception('Unexpected table status: %s' % desc['TableStatus'])
	return table


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def describe_table(table):
	return table.describe()


@backoff.on_exception(backoff.constant, [ConditionalCheckFailedException,
		ProvisionedThroughputExceededException])
def wait_and_activate(state):
	while state['state'] != 'idle':
		sleep(1)
		state = get_state(table)
	state['state'] = 'active'
	state.partial_save()


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def deactivate(state):
	state['state'] = 'idle'
	state.partial_save()


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def get_state(table, project):
	try:
		return table.get_item(project=project, consistent=True)
	except ItemNotFound:
		return Item(table, data={
			'project': project,
			'state': 'idle',
		})


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def mark_waiting(state, playbook):
	state.table.connection.update_item(
		table_name=TABLE,
	    key={'project': {'S': state['project']}},
	    update_expression='ADD waiting :playbook',
	    expression_attribute_values={':playbook': {'SS': [playbook]}},
	)


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def unmark_waiting(state, playbook):
	state.table.connection.update_item(
		table_name=TABLE,
	    key={'project': {'S': state['project']}},
	    update_expression='DELETE waiting :playbook',
	    expression_attribute_values={':playbook': {'SS': [playbook]}},
	)


def run_playbook(playbook):
	try:
		proc = Popen(['ansible-playbook', playbook], stdin=PIPE)
		proc.stdin.close()
		return proc.wait()
	finally:
		for _ in range(5):
			if proc.returncode is not None:
				break
			proc.terminate()
			sleep(1)
		else:
			proc.kill()


if __name__ == '__main__':
	project = os.environ['ANSIBLE_PROJECT']
	playbook = os.environ['ANSIBLE_PLAYBOOK']
	returncode = serialize(project, playbook)
	sys.exit(returncode)
