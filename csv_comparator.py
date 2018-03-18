import configparser
import argparse
import re
import os
import sys
from configuration import extract_man_field

""" Simple script to compare two csv files
    Input: two files to be compared: A|B
    Names can be provided as a cmd line args [a,b]
    Or by default script will iterate path [f] to find any csv with 
    Filesystem from configuration file in the name and try to make diff.
    
    Output is the diff csv file, with 'diff_" suffix and filesystem name. 
    As a result we got file C = B - A (A is reference version, B is consider as secondary)
"""


def prefix(x):
    return {
        'K': 1000,
        'k': 1000,
        'M': 1000000,
        'm': 1000000,
        'G': 1000000000,
        'g': 1000000000
    }.get(x, 1)


# 110 90 = (90 - 110)/110 * 100 == -18.18% change
def get_percent(a, b):
    try:
        return (float(b) - float(a))/float(b)*100
    except ZeroDivisionError:
        return 0.0

def get_diff_tag():
    return 'workload,%d(READ),%d(READ-aggrb),%d(WRITE),%d(WRITE-aggrb),%d(ios),d(cs-md),d(cs-av),d(us-md),d(us-av),' \
           'd(sy-md),d(sy-av),d(id-md),d(id-av),d(wa-md),d(wa-av) '


# Return new row created as a comparation of r1 and r2 based on pattern:
# workload,READ,READ-aggrb,WRITE,WRITE-aggrb,ios,cs-md,cs-av,us-md,us-av,sy-md,sy-av,id-md,id-av,wa-md,wa-av
# ...
# workload is not compared
# [READ:ios] [1:5]we compare on percentage basis
# [cs-md:wa-av] [6:15] we present as a delta
def compare_row(r1, r2, percent=True):
    r1 = r1.split(',')
    r2 = r2.split(',')
    if len(r1) != len(r2):
        sys.exit("Cannot compare two rows with different size, check input data")
    result = [0] * len(r1)
    result[0] = r1[0]
    for i in range(1, len(r1)):
        if percent:
            result[i] = get_percent(r1[i], r2[i])
        else:
            result[i] = float(r2[i]) - float(r1[i])
#   print(result)
    return result


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass

    return False


def cast_prefix(x):
    if not is_number(x[-1:]):
        b = int(x[:-1]) * prefix(x[-1])
    else:
        b = int(x)
    return b


# Format of tag is as follow: <workload>_N_jb_M<K/M>_bl_J_rw
# We return triple: [jobs: N, blksize: M, rw_rat: J]
def extract_tag(tag):
    lt = tag.split('_')
    jobs = int(lt[lt.index('jb')-1])
    blksize = cast_prefix(lt[lt.index('bl')-1])
    rat = int(lt[lt.index('rw')-1])
    return [jobs, blksize, rat]


def comp_triple(a, b):
    return a[0] == b[0] and a[1] == b[1] and a[2] == b[2]


def match_and_merge(f1, f2):
    # Lets do this in really dummy way because ...
    # we don't know if rows in csv are placed by test in the same order (we don't want to guarantee that)
    # Fix me after by applying any 'good' pattern
    merged = []
    for a in f1:
        at = extract_tag(a)
        for idx, bval in enumerate(f2):
            bt = extract_tag(bval)
            if comp_triple(at, bt):
                comp_tab = compare_row(a, bval)
                merged.append(str(comp_tab).strip('[]').strip('\n').replace("\'", ""))
                del(f2[idx])
                break
    return merged


# Should load 2 files with fs extension to compare
# Case when there are three or more files is not handled correctly
def load_fs_stats(fs, f1, f2):
    # Prepare output csv
    a_name = f1[1].split(',')[0].split('_')[:f1[1].split(',')[0].split('_').index('jb')-2]
    b_name = f2[1].split(',')[0].split('_')[:f2[1].split(',')[0].split('_').index('jb')-2]
    out = open('diff_{}_A{}_B{}.csv'.format(fs, '_'.join(a_name), '_'.join(b_name)), 'w')
    title = f1[0].split(',')
    first = title[0]
    title = list(map(lambda x: 'd'+x, title[1:]))
    title.insert(0, first)
    out.write(str(title).strip('[]').strip('"').replace('\\n', ''))
    out.write('\n')
    # drop title bar
    f1 = f1[1:]
    f2 = f2[1:]
    f3 = match_and_merge(f1, f2)

    # Get parameters lists
    config = configparser.ConfigParser()
    config.read('test_config.ini')

    num_jobs = list(map(int, config.get('test', 'num_jobs').split(',')))
    blks = list(map(lambda x: cast_prefix(x), config.get('test', 'blk_size').split(',')))
    mix_read = list(map(int, config.get('test', 'mix_read').split(',')))
    print("#: blocks list: ", list(blks))
    # Here we generate series of benchmark where we do iterate by parameters

    # split by rwmix
    for j in mix_read:
        fj = list(filter(lambda x: extract_tag(x)[2] == j, f3))
        # split by blk_size
        for b in blks:
            bn = list(filter(lambda x: extract_tag(x)[1] == b, fj))
            # iterate by jobs
            for n in num_jobs:
                jn = list(filter(lambda x: extract_tag(x)[0] == n, bn))
                if len(jn) > 0:
                    out.write(str(jn).strip('[]').strip('""'))
                    out.write('\n')

    out.close()


# Based on the tricky logic/input args find and return files to compare
def get_files_to_compare(fs, args):
    # result is a 2 elements list (reference file, secondary file)
    res = []

    # get root
    r = os.path.dirname(os.path.realpath(__file__))

    # If user explicitly specified A and B return these two files
    if args.reffile is not None and args.secfile is not None:
        res.append(open(os.path.join(r, args.reffile)).readlines())
        res.append(open(os.path.join(r, args.secfile)).readlines())
        return res

    # If user specified dir path extends root
    if args.filesdir is not None:
        r = os.path.join(r, args.filesdir)

    # filter log files, we need them to be in the files with csv file with:
    # 'parsed_' sufix and '_<fs>' prefix
    fs_logs = [f for f in os.listdir(r) if fs in f and os.path.isfile(os.path.join(r, f))]
    fs_logs = [f for f in fs_logs if '.csv' in f]

    sorted(fs_logs)

    if len(fs_logs) < 2:
        sys.exit('Not found logs to parse. Quiting')

    return [fs_logs[-2], fs_logs[-1]]


def get_fs_from_name(fname):
    # just do it in dummy way:
    fss = ['ext3', 'ext4', 'xfs', 'zfs', 'btrfs']
    for f in fss:
        if f in fname.lower():
            return f


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--config", type=open, default='test_config.ini', required=False,
                        dest="config", help="Test configuration.")
    parser.add_argument("-d", "--filesdir", default='./', required=False,
                        dest="files_directory", help="Where to search for csv to compare")
    parser.add_argument("-f", "--filesystems", nargs='+', required=False,
                        dest="filesystems", help="Filesystems to compare")
    parser.add_argument("-a", "--reffile", required=False, dest="reffile", help="Filesystems to compare")
    parser.add_argument("-b", "--secfile", required=False, dest="secfile", help="Filesystems to compare")

    config = configparser.ConfigParser()
    args = parser.parse_args()
    config.read(args.config.name)

    if args.reffile is not None and args.secfile is not None:
        files = get_files_to_compare('doesnt matter', args)
        fs_name = get_fs_from_name(files[0][1])
        load_fs_stats(fs_name, files[0], files[1])
        sys.exit('Diff generated')

    fs_list = args.filesystems
    if fs_list is None:
        fs_list = extract_man_field(config, 'test', 'fs2test')

    if isinstance(fs_list, str):
        fs_list = fs_list.split(',')

    for fs in fs_list:
        files = get_files_to_compare(fs, args)
        load_fs_stats(fs, files[0], files[1])
