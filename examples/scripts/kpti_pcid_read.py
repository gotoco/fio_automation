#!/usr/bin/env python3
import subprocess

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
        if fignore == 0:
            status = 1
            print('Cannot issue the command :: {}.\nError: {}'.format(cmd, e.output))
    if len(output) == 0:
        output = ''
    else:
        output = output.decode('utf-8')
    return {'status': status, 'output': output}


def main():
        kpti = 1
        pcid = 0
        cmd = 'cat /proc/cmdline'
        cmdline = perform_cmd(cmd, 0, 1, 0)['output']
        out = ''
        if 'pti=on' in out:
                kpti = 1
        else:
                cmd = 'dmesg | grep isolation'
                out = perform_cmd(cmd, 0, 1, 0)['output']
                if 'disabled' in out:
                        kpti = 0
                elif 'enabled' in out:
                        kpti = 1
                else:
                        cmd = 'cat /sys/kernel/debug/x86/pti_enabled'
                        out = perform_cmd(cmd, 0, 1, 0)['output']
                        if '1' == out:
                                kpti = 1
                        elif '0' == out:
                                kpti = 0

        cmd = 'cat /proc/cpuinfo | grep pcid'
        out = perform_cmd(cmd, 0, 1, 0)['output']
        if ('nopcid' in cmdline) and ('noinvpcid' in cmdline):
                pcid = 0
        elif ('pcid' in out) or ('invpcid' in out):
                pcid = 1
        else:
                cmd = 'cat /proc/cpuinfo | grep pcid'
                out = perform_cmd(cmd, 0, 1, 0)['output']
                if 'pcid' in out:
                        pcid = 1

        return 'test_kpti{}_pcid{}'.format(kpti, pcid)


if __name__ == "__main__":
        print(main())

