import os
import re
import sys


# Check for OS and export environment variables if OSX
if sys.platform == "darwin":
    os.environ['DYLD_LIBRARY_PATH'] = "$(brew --prefix openssl)/lib:$DYLD_LIBRARY_PATH"
elif os.path.exists('/etc/fedora-release'):
    os.environ['LD_LIBRARY_PATH'] = "/opt/openssl-compat-bitcoin/lib:$LD_LIBRARY_PATH"

# if being executed from installation into some base directory,
# we make sure we are running standing at this location
cmdline_args = "".join(sys.argv[1:])

if re.match('.*/bin/openbazaar.py$', sys.argv[0]):
    # Change to base dir and run openbazaar
    basedir = sys.argv[0].replace('/bin/openbazaar.py', '/share/openbazaar.py')
    os.system("(cd \"%s\" && python -m node.openbazaar \"%s\") &)" % (basedir, cmdline_args))
else:
    python_path = './env/bin/python'
    if os.path.exists(python_path) \
            and os.access(python_path, os.R_OK) \
            and os.access(python_path, os.X_OK):
        os.system("./env/bin/python -m node.openbazaar \"%s\" &" % cmdline_args)
    else:
        os.system("python -m node.openbazaar \"%s\" &" % cmdline_args)
