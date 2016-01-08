#!/bin/sh

ansible-playbook /serialize/init-serialize.yml

exec python /serialize/serialize.py
