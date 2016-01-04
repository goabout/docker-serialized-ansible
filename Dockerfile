FROM goabout/ansible

MAINTAINER Go About <tech@goabout.com>

# Install parameterized entrypoint
ADD https://github.com/jcassee/parameterized-entrypoint/releases/download/0.7.0/entrypoint_linux_amd64 /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint

# Install dependencies
RUN pip install backoff "boto<3"

# Install serialize script
COPY serialize.py /usr/local/bin/serialize-ansible-playbook
RUN chmod +x /usr/local/bin/serialize-ansible-playbook

# Default environment variable values
ENV ANSIBLE_PROJECT ansible
ENV AWS_REGION us-east-1

COPY boto.cfg /templates/etc/boto.cfg

ENTRYPOINT ["entrypoint", "--"]
CMD ["serialize-ansible-playbook"]
