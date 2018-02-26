import os
import sys
from statistics import median, mean


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


'''
# All parsing is returning triple of:
#  - test description (tag)
#  - value in csv row format
#  - description of the row
'''
# Return csv row description
def get_csv_description():
    return 'workload,READ,WRITE,ios,cs-md,cs-av,us-md,us-av,sy-md,sy-av,id-md,id-av,wa-md,wa-av'


def prefix(x):
    return {
        'K': 1000,
        'M': 1000000,
        'G': 1000000000
    }.get(x)


# Parse vmstat fio file field to integer, remove GB, MB, KB, B sufixes
# In case of error can forward control to user if intel == 1
def vmstat_parse_field(field, intel=0):
    try:
        eq_idx = field.index('=')+1
        ut_idx = field.find('B/s,')
        if ut_idx is -1:
            ut_idx = field.find('B,')
        txt = field[eq_idx:ut_idx]
        if txt[-1].isdigit():
            return txt
        else:
            return prefix(txt[-1])*float(txt[:-1])

    except Exception as ex:
        print("Sorry, Exception raised during parsing the field: {}\n".format(field))
        print("Exception: {}\n".format(ex))
        return input("You can still recover by providing manually value\n>>...")


# We need to extract from status files:
# READ-io, READ-aggrb
# WRITE-io, WRITE-aggrb
# Disk stats ios
def get_triple(f):
    # get 3 lines with results starting with READ, WRITE, and third after keyword
    # row title will looks as follow: 'READ, WRITE, ios'
    lines = []
    rw = {'READ', 'WRITE'}
    disk_stats = 'Disk stats (read/write):'
    ll = open(f, 'r', errors='replace').readlines()
    description = 'READ, WRITE, ios'

    for i in range(len(ll)):
        for k in rw:
            if k in ll[i]:
                lines.append(ll[i])
                break
        if disk_stats in ll[i]:
            lines.append(ll[i+1])

    if len(lines) != 3:
        sys.exit('Incorrect format of performance results.\nConsider checking perf logs.\nCannot Process...')

    csv = []
    # Process READ section
    tmp = lines[0].split()
    csv.append(vmstat_parse_field(tmp[1]))
    csv.append(vmstat_parse_field(tmp[2]))

    # Process WRITE section
    tmp = lines[1].split()
    csv.append(vmstat_parse_field(tmp[1]))
    csv.append(vmstat_parse_field(tmp[2]))

    # Process disk ios
    tmp = lines[2].split()
    csv.append(vmstat_parse_field(tmp[1]))

    return dict(title=f[f.rfind('/')+1:], description=description, csv_row=csv)


def parse_perf_files(stats_root):
    # Get all perf files from the stats_root
    files = [f for f in os.listdir(stats_root) if os.path.isfile(os.path.join(stats_root, f))]

    rows = []
    for f in files:
        # Skip swaps just in case :)
        if '.swp' in f:
            continue
        rows.append(get_triple(os.path.join(stats_root, f)))
        rows[-1] = parse_stats_files(stats_root, rows[-1])

    print(rows)
    return rows


# extract from vmstat file median for:
# 'cs, us, sy, id, wa' [11, 12, 13, 14, 15]
# TODO: FIX ME currently we just hardcode position inside vmstat output
#       But in future it will be good to find position dynamically
# Additional Note: during performing fio workload for some reason fio stuck for first few
#                  period of time and just doing write. To fix that we filter all
def vmstat_file_extract(path):
    lines = open(path, 'r', errors='replace').readlines()
    data = []
    for l in lines:
        d = l.split()
        if len(d) > 0 and d[0].isdigit():
            data.append(d)

    if len(data) < 2:
        sys.exit('Stats vmstat file empty, cannot continue!')

    # Remove first line as it contain time since vmrun (really bad for avg)
    del data[0]

    dt = {'cs': [], 'us': [], 'sy': [], 'id': [], 'wa': []}
    for i in data:
        dt['cs'].append(int(i[11]))
        dt['us'].append(int(i[12]))
        dt['sy'].append(int(i[13]))
        dt['id'].append(int(i[14]))
        dt['wa'].append(int(i[15]))

    csm = median(dt['cs'])
    usm = median(dt['us'])
    sym = median(dt['sy'])
    idm = median(dt['id'])
    wam = median(dt['wa'])

    csa = mean(dt['cs'])
    usa = mean(dt['us'])
    sya = mean(dt['sy'])
    ida = mean(dt['id'])
    waa = mean(dt['wa'])

    return [csm, csa, usm, usa, sym, sya, idm, ida, wam, waa]


# As for now we are interested in vmstat output
# for every workload correspond vmstat is saved in stat file,
# Here we combine them together
def parse_stats_files(stats_root, row):
    # Get followed data from vmstat (we calculate both median and avg):
    # cs : context switching counter from CPU
    # id : cpu idle time
    # wa : cpu waiting time
    # sy : percent of time spent inside system
    # us : percent of time spent inside user space code
    # row title will looks as follow: 'cs, us, sy, id, wa'
    title2 = ', cs-md, cs-av, us-md, us-av, sy-md, sy-av, id-md, id-av, wa-md, wa-av'

    # for row get stats folder and read vmstat
    path = os.path.join(stats_root, 'stats_'+row['title'])
    path = os.path.join(path, 'vmstat')
    data = vmstat_file_extract(path)
    row['description'] += title2
    row['csv_row'] += list(map(str, data))

    return row


def save_to_file(csv, tag, fs):
    file_name = 'parsed_{}_{}.csv'.format(tag, fs)
    print('Saving result to file')
    out = open(file_name, 'w')

    out.write(get_csv_description())
    out.write('\n')

    for row in csv:
        out.write(row['title'])
        out.write(',')
        out.write(','.join(map(str, row['csv_row'])))
        out.write('\n')
    out.close()


def parse(stats_root, fs):
    csv = parse_perf_files(stats_root)
    save_to_file(csv, stats_root[stats_root.rfind('/')+1:], fs)


def gen_stats_files(root, all, fs):
    # Clear flag just in case if something went wrong and we need to restore fs to clear
    for f in fs:
        stats_root = get_result_root(f, root, all)
        for s in stats_root:
            parse(s, f)


if __name__ == "__main__":
    fs_list = ['xfs', 'ext4', 'zfs']
    root = None
    all = 0
    # TODO: I am broken please use argpars!
    if len(sys.argv) > 1:
        arg1 = sys.argv[1]
        if arg1 is "--test_dir" and sys.argv > 2:
            root = sys.argv[2]
        if arg1 == "--all":
            all = 1
    print('#: all = {}'.format(all))
    gen_stats_files(root, all, fs_list)
