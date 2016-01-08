#!/usr/bin/env python

from __future__ import print_function

from ConfigParser import ConfigParser, NoSectionError
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
THROUGHPUT = {'read': 1, 'write': 1}


class Unbuffered(object):
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)

sys.stdout = Unbuffered(sys.stdout)
sys.stderr = Unbuffered(sys.stderr)


class ProjectActiveException(Exception):
	pass

class ProjectBlockedException(Exception):
	pass

class PlaybookWaitingException(Exception):
	pass


def serialize(project, playbook, config):
	table = get_table(config)

	try:
		state = wait_and_activate(table, project, playbook)
	except PlaybookWaitingException:
		print('Project "%s" playbook "%s" is already waiting' %
				(project, playbook))
		return
	except ProjectBlockedException:
		print('Project "%s" is blocked' % project)
		return

	try:
		return run_playbook(playbook)
	finally:
		deactivate(state)


def get_table(config):
	connection = connect_to_region(config.get('aws_region', 'us-east-1'),
		aws_access_key_id=config.get('aws_access_key_id'),
	    aws_secret_access_key=config.get('aws_secret_access_key'))
	table_props = {
		'table_name': TABLE,
		'schema': [HashKey('project')],
		'throughput': THROUGHPUT,
		'connection': connection,
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


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def get_state(table, project):
	try:
		return table.get_item(project=project, consistent=True)
	except ItemNotFound:
		state = Item(table, data={
			'project': project,
			'state': 'idle',
		})
		state.save()


def wait_and_activate(table, project, playbook):
	mark_waiting(table, project, playbook)
	try:
		print('Waiting for project "%s" playbook "%s" to become idle' %
				(project, playbook), end='')
		return activate(table, project, playbook, '.')
	finally:
		unmark_waiting(table, project, playbook)
		print()

@backoff.on_exception(backoff.constant, (ConditionalCheckFailedException,
		ProvisionedThroughputExceededException, ProjectActiveException))
def activate(table, project, playbook, progress_str):
	print('.', end='')

	try:
		state = table.get_item(project=project, consistent=True)
	except ItemNotFound:
		state = Item(table, data={
			'project': project,
			'state': 'idle',
		})

	if state['state'] == 'blocked':
		raise ProjectBlockedException()

	if state['state'] == 'active':
		raise ProjectActiveException()

	state['state'] = 'active'
	state.partial_save()
	return state


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def deactivate(state):
	state['state'] = 'idle'
	state.partial_save()


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def mark_waiting(table, project, playbook):
	try:
		table.connection.update_item(
			table_name=table.table_name,
		    key={'project': {'S': project}},
		    update_expression='ADD waiting :playbooks',
		    condition_expression='NOT contains(waiting, :playbook)',
		    expression_attribute_values={
		    	':playbook': {'S': playbook},
		    	':playbooks': {'SS': [playbook]},
	    	},
		)
		return True
	except ConditionalCheckFailedException:
		raise PlaybookWaitingException()


@backoff.on_exception(backoff.constant, ProvisionedThroughputExceededException)
def unmark_waiting(table, project, playbook):
	table.connection.update_item(
		table_name=table.table_name,
	    key={'project': {'S': project}},
	    update_expression='DELETE waiting :playbooks',
	    expression_attribute_values={':playbooks': {'SS': [playbook]}},
	)


def run_playbook(playbook):
	print('Running playbook')
	try:
		proc = Popen(['ansible-playbook', playbook])
		proc.wait()
		return proc.returncode
	finally:
		for _ in range(5):
			if proc.returncode is not None:
				break
			proc.terminate()
			sleep(1)
		else:
			proc.kill()


def load_config():
	path = os.path.dirname(os.path.abspath(__file__))
	config = ConfigParser()
	config.read(os.path.join(path, 'serialize.ini'))
	try:
		vars = {k: v for k, v in config.items('serialize') if v}
	except NoSectionError:
		vars = {}

	return {var: os.environ.get(var.upper(), vars.get(var)) for var in [
		'aws_access_key_id',
		'aws_secret_access_key',
		'aws_region',
	]}


if __name__ == '__main__':
	try:
		project = os.environ['ANSIBLE_PROJECT']
		playbook = os.environ['ANSIBLE_PLAYBOOK']
		config = load_config()
		returncode = serialize(project, playbook, config)
		sys.exit(returncode)
	except KeyboardInterrupt:
		print('Interrupted', file=sys.stderr)
		sys.exit(130)
