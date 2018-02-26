import configparser
import re
import os
import sys

#patched_kern = '3.10.0-693.17.1.el7'
patched_kern = '3.10.0-693.17.1.el7'
unpatched_kern = '3.10.0-693.17.1.el7'
#unpatched_kern = '3.10.0-693.el7'

def prefix(x):
    return {
        'K': 1000,
        'k': 1000,
        'M': 1000000,
        'm': 1000000,
        'G': 1000000000,
        'g': 1000000000
    }.get(x, 1)


# 100 90 = (90 - 100)/100 * 100 == -10% change
def get_percent(a, b):
    return (float(b) - float(a))/float(b)*100


def get_diff_tag():
    return 'workload,%d(READ),%d(READ-aggrb),%d(WRITE),%d(WRITE-aggrb),%d(ios),d(cs-md),d(cs-av),d(us-md),d(us-av),' \
           'd(sy-md),d(sy-av),d(id-md),d(id-av),d(wa-md),d(wa-av) '


# Return new row created as a comparation of r1 and r2 based on pattern:
# workload,READ,READ-aggrb,WRITE,WRITE-aggrb,ios,cs-md,cs-av,us-md,us-av,sy-md,sy-av,id-md,id-av,wa-md,wa-av
# ...
# workload is not compared
# [READ:ios] [1:5]we compare on percentage basis
# [cs-md:wa-av] [6:15] we present as a delta
def compare_row(r1, r2):
    r1 = r1.split(',')
    r2 = r2.split(',')
    if len(r1) != len(r2):
        sys.exit("Cannot compare two rows with different size, check input data")
    result = [0] * len(r1)
    result[0] = r1[0][:r1[0].find('3.10.0')-1]
    for i in range(1, len(r1)):
        if i < 5:
            result[i] = get_percent(r1[i], r2[i])
        elif i == 5:
            r1io1 = r1[i][:r1[i].index('/')]
            r1io2 = r1[i][r1[i].index('/')+1:]
            r2io1 = r2[i][:r2[i].index('/')]
            r2io2 = r2[i][r2[i].index('/')+1:]
            result[i] = '{}/{}'.format(get_percent(r1io1, r2io1), get_percent(r1io2, r2io2))
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


# Format of tag is as follow: <workload>_N_jobs_M<K/M>_blks_J_rrat
# We return triple: [jobs: N, blksize: M, rw_rat: J]
def extract_tag(tag):
    jobs = int(re.search("_(.+?)_jobs", tag).group(1))
    blksize = re.search("jobs_(.+?)_blks", tag).group(1)
    blksize = cast_prefix(blksize)
    rat = int(re.search("blks_(.+?)_rrat", tag).group(1))
    return [jobs, blksize, rat]


def comp_triple(a, b):
    return a[0] == b[0] and a[1] == b[1] and a[2] == b[2]


def match_and_merge(f1, f2):
    # Lets do this in really dummy way
    # Fix me after by applying any 'good' pattern
    merged = []
    for a in f1:
        at = extract_tag(a)
        for idx, bval in enumerate(f2):
            bt = extract_tag(bval)
            if comp_triple(at, bt):
                comp_tab = compare_row(a, bval)
                merged.append(a+','+bval+','+str(comp_tab).strip('[]'))
                del(f2[idx])
                break
    return merged




# Should load 2 files with fs extension to compare
# Case when there are three or more files is not handled correctly
def load_fs_stats(fs):
    # get root
    r = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'result')
    fs_logs = [f for f in os.listdir(r) if fs in f and os.path.isfile(os.path.join(r, f))]

    # f1 will be filled with unpatched kernel logs
    # f2 with unpatched kernel logs
    for idx, val in enumerate(fs_logs):
        with open(os.path.join('result', val)) as f:
            content = f.readlines()

        content = [x.strip() for x in content]
        if idx == 0:
            f1 = content
        else:
            f2 = content
##        if True in map(lambda x: unpatched_kern in x, content):
##            f1 = content
##        else:
##            f2 = content
    # Prepare output csv
    out = open('test_compare_{}.csv'.format(fs), 'w')
    title = f1[0]+','+f1[0]+','+get_diff_tag()
    out.write(title)
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
                out.write(str(jn).strip('[]').strip('""'))
                out.write('\n')

    out.close()


load_fs_stats('xfs')
#load_fs_stats('ext4')
