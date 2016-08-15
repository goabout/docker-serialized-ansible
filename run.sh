#!/bin/sh

ansible-playbook init-serialize.yml

exec python /serialize/serialize.py
