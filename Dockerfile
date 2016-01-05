FROM goabout/ansible

MAINTAINER Go About <tech@goabout.com>

# Install dependencies
RUN pip install backoff "boto<3"

# Install serialize script
COPY serialize.py /usr/local/bin/serialize-ansible-playbook
RUN chmod +x /usr/local/bin/serialize-ansible-playbook

# Default environment variable values
ENV ANSIBLE_PROJECT ansible

CMD ["serialize-ansible-playbook"]
