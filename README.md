Docker Serialized Ansible image
===============================

This project contains a Docker image for serializing Ansible runs.


## Usage

    docker run
    	-v $PWD:/ansible:ro \
    	-e ANSIBLE_PROJECT=myproject \
    	-e ANSIBLE_PLAYBOOK=playbook.yml \
    	-e AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE \
    	-e AWS_SECRET_ACCESS_KEY_ID=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
    	goabout/ansible

Mount the directory containing your playbooks at `/ansible`. By default, the
container will run the `site.yml` playbook. This can be changed using the
`ANSIBLE_PLAYBOOK` environment variable.

Using AWS [DynamoDB](https://aws.amazon.com/dynamodb/), the container makes sure
only one playbook is run concurrently for any project. If the same playbook is
already waiting to be run, the container exits immediately. Use environment
variables to set the AWS credentials.


## Environment variables

* **ANSIBLE_PROJECT**: The Ansible project name (default: `ansible`). Playbooks
                       from different projects are allowed to run concurrently.
* **ANSIBLE_PLAYBOOK**: The playbook to run (default: `site.yml`).
* **AWS_ACCESS_KEY_ID**: The AWS accesss key used to access DynamoDB.
* **AWS_SECRET_ACCESS_KEY**: The AWS access key used to access DynamoDB.
* **AWS_REGION**: The DynamoDB table region (default: `us-east-1`).
