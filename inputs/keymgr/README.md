Place each Lustre server's KMIP certificate files here, in a folder named
after the server's inventory name (ossnode1, ossnode2, mdsnode1, mdsnode2):

    inputs/keymgr/ossnode1/certauth.pem
    inputs/keymgr/ossnode1/clientkey.pem
    inputs/keymgr/ossnode1/clientcert.pem
    ...

tasks/keymgr-config.yml installs them to /etc/racktop/keymgrd/. This directory is
ignored by git, since clientkey.pem is a private key.
