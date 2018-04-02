#!/usr/bin/env python3
import os
import sys
import configparser
import argparse
from statistics import median, mean
from file_parser import file_parser
from configuration import extract_man_field
from configuration import get_fslist


def request_user_input(root, list):
    print('#: Found multiple results: {}'.format(list))

    var = input("#: Please specify folder with results...\n>> ")
    while not os.path.exists(root + '/' + var):
        var = input(" Please specify correct file: {}".format(list))

    return var


def get_result_root(fs, fs_dir=None, all=0):
    if fs_dir is None:
        fs_dir = os.path.dirname(os.path.realpath(__file__)) + '/' + fs
    else:
        fs_dir += '/' + fs
    files = [f for f in os.listdir(fs_dir) if os.path.isdir(os.path.join(fs_dir, f))]
    print(files)
    print(os.path.join(fs_dir, files[0]))

    if all is 0 and 1 < len(files):
        f = [request_user_input(fs_dir, files)]
    else:
        f = files

    res = []
    for fi in f:
        print(os.path.join(fs_dir, fi))
        res.append(os.path.join(fs_dir, fi))

    return res


function_mappings = {
    'avg': mean,
    'med': median
}


def select_function(string):
    return function_mappings[string]


def prefix(x):
    return {
        'K': 1024,
        'k': 1024,
        'Ki': 1000,
        'ki': 1000,
        'M': 1048576,
        'm': 1048576,
        'Mi': 1000000,
        'mi': 1000000,
        'G': 1073741824,
        'g': 1073741824,
        'Gi': 1000000000,
        'gi': 1000000000
    }.get(x)


def get_prexif_pos(string):
    for i in range(0, len(string)):
        if string[i] == '.':
            continue
        if not string[i].isdigit():
            return i
    return -1


# Parse vmstat fio file field to integer, remove GB, MB, KB, B sufixes
# In case of error can forward control to user if intel == 1
def parse_field(field, intel=0):
    try:
        eq_idx = field.find('=') + 1
        if eq_idx == -1:
            eq_idx = 0
        ut_idx = field.find('B/s')
        if ut_idx is -1:
            ut_idx = field.find('B')
        txt = field[eq_idx:ut_idx]
        if txt[-1].isdigit():
            return txt
        else:
            idx = get_prexif_pos(txt)
            return prefix(txt[idx:]) * float(txt[:idx])

    except Exception as ex:
        print("Sorry, Exception raised during parsing the field: {}\n".format(field))
        print("Exception: {}\n".format(ex))
        return input("You can still recover by providing manually value\n>>...")


def parse_monitor_files(stats_root, cfg):
    # Get all perf files from the stats_root
    files = [f for f in os.listdir(stats_root) if os.path.isfile(os.path.join(stats_root, f))]
    parser = file_parser()
    res = []
    for f in files:
        tmp = {}
        # Skip swaps just in case :)
        if '.swp' in f:
            continue
        # Currently we support only FIO output and vmstat output
        tmp.update({'fio_out': parser.parse(file_parser.FILE_FIO_OUT, os.path.join(stats_root, f))})
        tmp.update(
            {'vms_out': parser.parse(file_parser.FILE_VMSTAT, os.path.join(stats_root, 'stats_{}/vmstat'.format(f)))})
        tmp.update({'test': f})
        res.append(tmp)

    print(res)
    return res


def parse_fio_fields(fio, fields):
    res = {}
    for key, value in fields.items():
        res.update({key: parse_field(fio[value], 0)})

    return res


def vms_range(values, length):
    for i in range(0, len(values)):
        if '%' in values[i]:
            values[i] = float(values[i].strip('%')) / 100 * length
        else:
            if is_blank(values[i]):
                if i == 0:
                    values[i] = 0
                else:
                    values[i] = length
            else:
                values[i] = int(values[i])

    return slice(values[0], values[1])


def is_blank(myString):
    if myString and myString.strip():
        return False
    return True


def parse_vms_fields(vms, fields, vmstat_fields):
    res = {}
    vmsr = dict(map(lambda x: (int(x[x.find('('):x.find(')') + 1].strip('()')), x[x.find('[') + 1:x.find(']')]),
                    vmstat_fields.split(';')))

    for key, value in fields.items():
        row = list(map(lambda x: int(x), vms[value]))
        form = vmsr[key].split(',')
        s = vms_range(form[0].strip('()').split(':'), len(row))
        funct = select_function(form[1])
        res.update({key: funct(row[s])})

    return res


# If config specify perf fields
# Just get number of perf counters and name them p0-pN
def get_perf_fields(cfg, stats):
    perf_fields = extract_man_field(cfg, 'csv_output', 'perf_fields')
    number = 0
    if perf_fields == '(all)':
        if 'perf_cnt' in stats[0]['fio_out'].keys():
            number = len(stats[0]['fio_out']['perf_cnt'])
    res = ''
    for i in range(0, number):
        res += ',p{}'.format(i)
    return res


def generate_csv(stats, cfg):
    csv = []
    csv_header = extract_man_field(cfg, 'csv_output', 'csv_header')
    perf_fields = get_perf_fields(cfg, stats)
    csv_header += perf_fields
    csv.append(csv_header)

    fio_fields = extract_man_field(cfg, 'csv_output', 'fio_output')
    # Get fio_fields in order:
    fio_fields = fio_fields.split(';')
    # TODO: Handle other stats based on configuration
    # TODO: Handle other cases if not (1_NAME) but (1)NAME:A...
    fior = list(map(lambda x: x[x.find('('):x.find(')') + 1].strip('()'), fio_fields))
    fiod = dict(zip(map(lambda x: int(x[:x.find('_')]), fior), map(lambda x: x[x.find('_') + 1:], fior)))
    vmstat_fields = extract_man_field(cfg, 'csv_output', 'vmstat_fields')
    vmsr = map(lambda x: (int(x[x.find('('):x.find(')') + 1].strip('()')), x[x.find(')') + 1:x.find('[')]),
               vmstat_fields.split(';'))
    vmsd = dict(vmsr)
    # this require python3.5
    orderz = {**vmsd, **fiod}
    maxz = max(orderz)

    for i in stats:
        row = ''
        test = i['test']
        row += '{},'.format(test)
        fio = parse_fio_fields(i['fio_out'], fiod)
        vms = parse_vms_fields(i['vms_out'], vmsd, vmstat_fields)

        for j in range(1, maxz + 1):
            if j in fio:
                row += '{},'.format(fio[j])
            elif j in vms:
                row += '{},'.format(vms[j])
        if len(perf_fields) > 0:
            # remove double colon
            row = row[:-1]
            for k in range(0, len(i['fio_out']['perf_cnt'])):
                row += ',{}'.format(i['fio_out']['perf_cnt'][k])
        csv.append(row)

    return csv


def save_to_file(csv, tag, fs):
    file_name = 'parsed_{}_{}.csv'.format(tag, fs)
    print('Saving result to file {}'.format(file_name))
    out = open(file_name, 'w')

    for row in csv:
        out.write(row.strip(','))
        out.write('\n')
    out.close()


def get_tag(stats_root, config):
    files = [f for f in os.listdir(stats_root) if os.path.isfile(os.path.join(stats_root, f))]
    workload = config.get('test', 'workload').split(',').sort(key=len, reverse=True)
    res = []
    if len(files) < 1:
        return 'ERROR'

    for f in files:
        # Skip swaps just in case :)
        if '.swp' in f:
            continue
        os.path.join(stats_root, f)
        res.append((lambda x: '_'.join(x[:x.index(workload)]))(f.split('_')))
    # Get middle element right now
    return res[int(len(res)/2)]


def parse(stats_root, fs, config):
    tag = get_tag(stats_root, config)
    stat = parse_monitor_files(stats_root, config)
    csv = generate_csv(stat, config)
    save_to_file(csv, stats_root[stats_root.rfind('/') + 1:] + '_' + tag, fs)


def gen_stats_files(root, all, fs, config):
    # Clear flag just in case if something went wrong and we need to restore fs to clear
    for f in fs:
        stats_root = get_result_root(f, root, all)
        for s in stats_root:
            parse(s, f, config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--config", type=open, default='test_config.ini', required=False,
                            dest="config", help="Test configuration.")
    parser.add_argument("-d", "--test_dir", default='', required=False,
                        dest="testdir", help="Directory with results to parse.")
    config = configparser.ConfigParser()
    args = parser.parse_args()
    config.read(args.config.name)

    fs_list = get_fslist(config)
    root = None
    all = 0

    if args.testdir:
            root = args.testdir
            all = 1

    gen_stats_files(root, all, fs_list, config)
