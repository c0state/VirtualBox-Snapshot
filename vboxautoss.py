import datetime
import logging
import optparse
import re
import shlex
import socket
import string
import subprocess

import loghandlers

global custlogger
custlogger = None

def get_vm_list():
    # get list of tuples of (machine_name, machine_uuid)
    
    try:
        cmd = '"%s" list vms' % options.vboxmanage_path
        vmslist = subprocess.check_output(cmd)
                
        for line in str.splitlines(vmslist):
            # vboxmanage list vms result is 'machine_name {uuid}'
            names = shlex.split(line)
            
            # strip off begin and end curly braces
            names[1] = names[1][1:-1]
            
            yield names
            
    except Exception as err:
        custlogger.error("Couldn't get list of virtual machines from VirtualBox--" \
                         "error message was [%s]" % (err))
        raise err
    
def get_snapshots(name):
    """
    Get list of snapshots for given machine name/uuid
    """
    
    try:
        cmd = '"%s" showvminfo "%s"' % (options.vboxmanage_path, name)
        cmdoutput = subprocess.check_output(cmd)
        
        found_snapshot_string = False
        for line in str.splitlines(cmdoutput):
            if line.strip() == "":
                continue
            
            if re.match("Snapshots:", line):
                found_snapshot_string = True
                continue
            
            if found_snapshot_string:
                mobj = re.match("\s*Name: (.*) \(UUID: (.*)\)", line)
                if mobj:
                    yield mobj.group(1, 2)
                # no more snapshots found, exit loop
                else:
                    break
                
    except Exception as err:
        custlogger.error("Couldn't get list of snapshots for machine [%s]--error was [%s]" % 
                         (name, err))
        raise err

def delete_snapshot(vmid, ssuuid):
    try:
        custlogger.warning("Deleting snapshot [%s] for VM [%s]" % (ssuuid, vmid))
        
        cmd = '"%s" snapshot "%s" delete "%s"' % (options.vboxmanage_path, vmid, ssuuid)
        cmdoutput = subprocess.check_output(cmd)
    except Exception as err:
        custlogger.error("Couldn't delete snapshot [%s] for machine [%s]--error was [%s]" % 
                         (ssuuid, vmid, err))
        raise err

def configure_logger(smtpserver, smtpserverport, user, passwd, logemail, secure):
    global custlogger
    custlogger = logging.getLogger("log_stdout_and_email")
    custlogger.setLevel(logging.DEBUG)
    
    # set up stdout logger
    stdouthandler = logging.StreamHandler()
    logformat = logging.Formatter("[%(asctime)s] [%(levelname)8s] --- %(message)s (%(filename)s:%(lineno)s)", "%Y-%m-%d %H:%M:%S")
    stdouthandler.setFormatter(logformat)
    custlogger.addHandler(stdouthandler)

    if smtpserver:
        try:
            # handler to email specified address
            hostname = socket.gethostname()
            secureparam = None
            if secure:
                secureparam = ()
            mailloghandler = loghandlers.BufferingSMTPHandler((smtpserver, smtpserverport), "vboxautoss@%s" % (hostname), 
                                                          logemail, 
                                                          "vboxautoss script output for host [%s]" % hostname,
                                                          (user, passwd),
                                                          secureparam)
            mailloghandler.setFormatter(logformat)
            custlogger.addHandler(mailloghandler)
        except Exception as err:
            custlogger.error("Could not send logs to specified email address; please check configuration--error was [%s]" % (err))
            raise err
        
def parse_options():
    parser = optparse.OptionParser()
    parser.add_option("--vboxmanage_path",
                      type = "string", 
                      default="vboxmanage",
                      help="Full path to VBoxManage utility")
    parser.add_option("--snapshot_vms", 
                      action = "store_true",
                      default = False,
                      help="Take a snapshot of each machine in VirtualBox")
    parser.add_option("--prune_snapshots", 
                      type = "int",
                      default = 0,
                      help="Prune oldest snapshots until n are left")
    parser.add_option("--smtp_server", 
                      type = "string",
                      help="SMTP to send logs via email")
    parser.add_option("--smtp_server_port", 
                      type = "int",
                      default = "465",
                      help="SMTP server port")
    parser.add_option("--smtp_user", 
                      type = "string",
                      help="User on SMTP server")
    parser.add_option("--smtp_passwd", 
                      type = "string",
                      help="Password for user on SMTP server")
    parser.add_option("--email", 
                      type = "string",
                      help="User to email log to")
    parser.add_option("--smtp_secure", 
                      action = "store_true",
                      default = False,
                      help="Use secure SSL/TLS login on SMTP server")
    return parser.parse_args()
    
if __name__ == "__main__":
    (options, args) = parse_options()
    
    configure_logger(options.smtp_server, options.smtp_server_port,
                     options.smtp_user, options.smtp_passwd, 
                     options.email, options.smtp_secure)
    
    if options.snapshot_vms:
        # go through lists of vms
        for (vmname, vmuuid) in get_vm_list():
            ssname = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            custlogger.info("Taking snapshot for vm [%s] with name [%s]" % (vmname, ssname))
            
            subprocess.check_output('"%s" snapshot "%s" take "%s"' % 
                                    (options.vboxmanage_path, vmname, ssname))
        
    if options.prune_snapshots > 0:
        for (vmname, vmuuid) in get_vm_list():
            vmss = list(get_snapshots(vmuuid))
            custlogger.info("VM [%s] has [%s] snapshots" % (vmname, len(vmss)))
            
            for (ssname, ssuuid) in vmss:
                custlogger.info("VM [%s] has snapshot named [%s] with UUID [%s]" % (vmname, ssname, ssuuid))

            # number of snapshots to prune
            del_ss_count = len(vmss) - options.prune_snapshots
            if del_ss_count > 0:
                custlogger.info("Will delete [%s] snapshots for VM [%s]" % (del_ss_count, vmname))
                
                for i in xrange(0, del_ss_count):
                    delete_snapshot(vmname, vmss[i][1])
