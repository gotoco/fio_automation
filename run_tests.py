#!/usr/bin/env python3

import subprocess
import shlex
import configparser
import sys
import os, os.path
import signal
import errno
import argparse
from time import gmtime, strftime, sleep
from result_parser import gen_stats_files
from configuration import extract_man_field
from configuration import get_fslist


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def safe_open_w(path):
    ''' Open "path" for writing, creating any parent directories as needed.
    '''
    mkdir_p(os.path.dirname(path))
    return open(path, 'w')


def get_kernel_version():
    out = perform_cmd('uname -r', 0, 0)
    return out['output'].decode('ascii').rstrip('\n')


# Perform bash command
# Additional args:
# @verbose : if 1 simply print command before performing it
# @fignore : if 1 ignore any status from bash and simply return success
# @redrall : if 1 redirect all to STDIN (simply 2>&1 at the end of command)
#               Useful with time and perf run with commands
def perform_cmd(cmd, verbose=0, fignore=0, redirall=0):
    status = 0
    output = ''
    if redirall == 1:
        cmd += ' 2>&1'
    if verbose != 0:
        print(cmd)

    try:
        output = subprocess.check_output(['bash', '-c', cmd])
    except subprocess.CalledProcessError as e:
        print('Cannot issue the command :: {}.\nError: {}'.format(cmd, e.output))
        if fignore == 0:
            status = 1

    return {'status': status, 'output': output}


def run_stat_cmd(cmd, path, args=[]):
    f = safe_open_w(path + "/" + cmd)
    a = ' '.join(map(str, args))
    cmd = '{} {}'.format(cmd, a)
    p = subprocess.Popen(shlex.split(cmd), stdout=f)
    return p.pid


def start_monitoring(dir_name, fs, interval):
    pid_list = {
        'vmstat': run_stat_cmd('vmstat', dir_name, [interval]),
        'mpstat': run_stat_cmd('mpstat', dir_name, ['-A', interval]),
        'iostat': run_stat_cmd('iostat', dir_name, ['-x', '-d', interval]),
        'sar': run_stat_cmd('sar', dir_name, ['-A', '-o {}/sarasc'.format(dir_name), interval, 10000])}

    return pid_list


def stop_monitoring(pid_list):
    for key, pid in pid_list.items():
#        print("#: killing {} with pid: {}".format(key, pid))
        os.kill(pid, signal.SIGKILL)


def gen_tag(test_name, workload, num_jobs, blk_size, fs, rwmix=0):
    kernel = get_kernel_version()
    return '{}_{}_{}_jb_{}_bl_{}_rw_{}_{}'.format(test_name, workload, num_jobs, blk_size, rwmix, fs, kernel)


# Append to cmd field from config
def append_flag_to_cmdparams(cmd, config, test, property, flag_name):
    # Extract property from given test, if field not available just skip
    if config.has_option(test, property):
        val = config.get(test, property)
        # if value empty, it is just silently skipped
        if val != '':
            cmd += ' --{}={}'.format(flag_name, val)
    else:
        print('Parser: field not specified {} from {} skipping property\n'.format(property, test))

    return cmd


def append_spec_cmds(cmd, config):
    run_with_perf = bool(extract_man_field(config, 'monitoring', 'run_with_perf'))
    run_with_time = bool(extract_man_field(config, 'monitoring', 'run_with_time'))

    if run_with_perf:
        perf_args = extract_man_field(config, 'monitoring', 'perf_args')
        cmd = 'perf {} {}'.format(perf_args, cmd)

    if run_with_time:
        cmd = 'time {}'.format(cmd)

    return cmd


# Simple mapping fields from config to fio binary
# List fields from config should be iterate internally and passed as a parameters
#
# Currently Iterable parameters (called from outside)
# Other parameters will be extracted from config file
# @fs : FileSystem
# @nr_jobs : Number of jobs
# @f_size : Size of file
# @mix_read : Ratio R/W
# @spec_cmds : FIO can also be run inside perf monitoring or with time this param
#               describe if we want to run inside perf (or time, or both)
#
# (This parameter list can be changed to dictionary later if required)
def perform_fio(config, fs, nr_jobs, blk_size, f_size, mix_read, spec_cmds=False):
    # Extract configuration
    try:
        test_name = config.get('test', 'test_name')
        workload = config.get('test', 'workload')
        run_time = config.get('test', 'run_time')
        directory = config.get('test', 'directory')
        direct = config.get('test', 'direct')
        interval = config.get('test', 'interval')
    except configparser.NoOptionError as ex:
        print('Error during configuration parsing!\nMandatory field missing:\n{}'.format(ex))
        return

    # tag is for marking the result
    tag = gen_tag(test_name, workload, nr_jobs, blk_size, fs, mix_read)
    pids = start_monitoring('stats_' + tag, fs, interval)

    print("performing io")
    cmd = './fio --name={} --bs={} --rw={} --size={} --numjobs={} ' \
          '--runtime={} --time_based --directory={} --output={} --direct={} '. \
        format(test_name, blk_size, workload, f_size, nr_jobs, run_time, directory, tag, direct)

    if mix_read != -1:
        cmd += ' --rwmixread={}'.format(mix_read)

    cmd = append_flag_to_cmdparams(cmd, config, 'test', 'ioengine', 'ioengine')

    cmd = append_flag_to_cmdparams(cmd, config, 'test', 'iodepth', 'iodepth')

    if config.has_option('test', 'additional_cmd'):
        val = config.get('test', 'additional_cmd')
        if val != '':
            cmd += ' {}'.format(val)

    if spec_cmds:
        cmd = append_spec_cmds(config, cmd)

    out = perform_cmd(cmd, 1, 1)
    if out['status'] != 0:
        print('#: warning fio returned error {}\n'.format(out['output']))

    # After IO close monitoring
    stop_monitoring(pids)

    # If any additional commands were run put outstanding output to the input file
    if spec_cmds is True:
        f_out = open(tag, 'w')
        f_out.write(out['output'])
        f_out.close()

    return


def lvm_setup(config, fs_type):
    drives = config.get('setup', 'drives').split(',')
    nr_strips = len(drives)
    dev_name = config.get('setup', 'dev_name')
    mnt_root = config.get('setup', 'mount_root')
    disk_group_name = config.get('setup', 'disk_group_name')
    lvm_path = '/dev/mapper/{}-{}'.format(dev_name, disk_group_name)
    devices = ' '.join(list(map((lambda x: '/dev/' + x), drives)))

    cmd = "vgcreate --yes {} {}".format(dev_name, devices)
    print(cmd)
    subprocess.check_output(['bash', '-c', cmd])

    cmd = "lvcreate --yes --stripes {} --stripesize 256 --extents 100%FREE --name {} {}" \
        .format(nr_strips, disk_group_name, dev_name)
    print(cmd)
    subprocess.check_output(['bash', '-c', cmd])

    cmd = "mkfs -t {} {}".format(fs_type, lvm_path)
    print(cmd)
    subprocess.check_output(['bash', '-c', cmd])

    cmd = "mount -t {} {} {}".format(fs_type, lvm_path, mnt_root)
    print(cmd)
    subprocess.check_output(['bash', '-c', cmd])


def lvm_destroy(config):
    dev_name = config.get('setup', 'dev_name')
    mnt_root = config.get('setup', 'mount_root')
    disk_group_name = config.get('setup', 'disk_group_name')
    drives = list(map((lambda x: '/dev/' + x), config.get('setup', 'drives').split(',')))

    cmd = "umount /{}".format(mnt_root)
    out = perform_cmd(cmd, 1)

    if out['status'] != 0:
        print("Error: cannot umount from folder {}!\n".format(mnt_root))

    cmd = "lvremove -f /dev/{}/{}".format(dev_name, disk_group_name)
    out = perform_cmd(cmd, 1)

    if out['status'] != 0:
        print("Error: cannot remove lvm device at /dev/{}/{}!\n".format(dev_name, disk_group_name))

    cmd = "vgremove -f {}".format(dev_name)
    out = perform_cmd(cmd, 1)

    if out['status'] != 0:
        print("Error: cannot remove volume group /dev/{}!\n".format(dev_name))

    # remove lvm labels from physical devices
    for d in drives:
        cmd = "pvremove -y -ff {}".format(d)
        out = perform_cmd(cmd, 1)

        if out['status'] != 0:
            print("Error: cannot wipe lvm label from {}!\n".format(d))


def zfs_setup(config):
    drives = config.get('setup', 'drives').split(',')
    mnt_root = config.get('setup', 'mount_root')
    disk_group_name = config.get('setup', 'disk_group_name')
    devices = ' '.join(list(map((lambda x: '/dev/' + x), drives)))

    res = perform_cmd("zpool create -f {} {}".format(disk_group_name, devices), 1)
    if res['status'] != 0:
        sys.exit("Error: cannot create ZFS pool: {}\n Closing".format(res['output']))

    res = perform_cmd("zfs set mountpoint={} {}".format(mnt_root, disk_group_name), 1)
    if res['status'] != 0:
        sys.exit("Error: cannot set ZFS mountpoint!\n{}\n Closing".format(res['output']))

    return


def zfs_destroy(config):
    disk_group_name = config.get('setup', 'disk_group_name')

    res = perform_cmd("zpool destroy {}".format(disk_group_name), 1)
    if res['status'] != 0:
        print("Error: cannot destroy ZFS pool: {}\n Closing".format(res['output']))

    return


def wipe_drives(config):
    drives = config.get('setup', 'drives').split(',')
    for d in drives:
        cmd = "dd if=/dev/zero of=/dev/{} bs=1024 count=65535".format(d)
        if perform_cmd(cmd, 1)['status'] != 0:
            sys.exit("Error: cannot clear drive: {}\n Closing".format(d))


def check_spec_cmds(config):
    run_with_perf = bool(extract_man_field(config, 'monitoring', 'run_with_perf'))
    run_with_time = bool(extract_man_field(config, 'monitoring', 'run_with_time'))

    return run_with_perf or run_with_time


def run_test(config, fs):
    # Verbose command to see where we are placing our stuff
    dummy = "ls -alhtri"
    output = subprocess.check_output(['bash', '-c', dummy])
    print(output.decode('ascii'))

    num_jobs = extract_man_field(config, 'test', 'num_jobs').split(',')
    blks = extract_man_field(config, 'test', 'blk_size').split(',')
    f_size = extract_man_field(config, 'test', 'file_size').split(',')
    mix_read = extract_man_field(config, 'test', 'mix_read').split(',')

    spec_cmd = check_spec_cmds(config)

    for fst in f_size:
        for job in num_jobs:
            for block in blks:
                for r in mix_read:
                    # Perform FIO test and do system monitor in the meantime
                    perform_fio(config, fs, job, block, fst, r, spec_cmd)
                    sleep(5)


def move_results(fs, config):
    workload = config.get('test', 'workload')
    time = strftime("%Y-%m-%d_%H:%M:%S", gmtime())
    path = '{}/{}'.format(fs, time)
    cmd = 'mkdir -p {}'.format(path)
    perform_cmd(cmd)

    cmd = 'mv `ls | grep {} | grep {}` {}'.format(workload, fs, path)
    perform_cmd(cmd, 1, 1)


def main(fs_list, config, nformat):
    if nformat is False:
        print("#: Warning nformat option chosen, after tests FS won't be clean up")
        print("\tnformat will run only test for first FS, as it doesn't make sense to loop")

        run_test(config, fs_list[0])
        move_results(fs_list[0], config)
        return

    for fs in fs_list:
       if fs == 'zfs':
           zfs_setup(config)
       else:
           lvm_setup(config, fs)

       run_test(config, fs)
       move_results(fs, config)

       if fs == 'zfs':
           zfs_destroy(config)
       else:
           lvm_destroy(config)


def clear_only(config):
    zfs_destroy(config)
    lvm_destroy(config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--clear", action="store_true", required=False,
                        help="Do disk cleanup. Try to remove all created structures")
    parser.add_argument("-p", "--config", type=open, default='test_config.ini', required=False,
                        dest="config", help="Test configuration.")
    parser.add_argument("-n", "--nformat", action="store_true", default=False, required=False,
                        dest="nformat", help="Do format and disk setup before test.")

    args = parser.parse_args()
    config = configparser.ConfigParser()
    config.read(args.config.name)

    fs_list = get_fslist(config)

    # Clear flag should be used in case if something went wrong
    # and we need to restore fs to clear state
    if args.clear:
        clear_only(config)
        sys.exit('Cleanup done! Finishing...')

    main(fs_list, config)
    gen_stats_files(None, 1, fs_list, config)
