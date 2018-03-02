# Simple Python Wrapper around FIO to perform automation
This simple wrapper runs FIO tests for 3 file systems 
and give results that can be easily comparable.
Currently, 3 FS that are supported: XFS, EXT4 and ZFS.

FIO automation allow running multiple tests with different parameters
across different filesystems, and parse results to CSV file.
Also, automation can compare the corresponding CSV and create diffs (in CSV format).

I wrote it originally because I had to run for over different parameters and 
compare results, find dimensions where FS performance had some regression.
That task even having shell scripts was not straightforward and required some
manual work which often resulted in introduction additional human error.
One day I decided to remove all glue scripts and write automation from scratch,
so here you go...

## Requirements:

### FIO

Compatible (and tested) with fio 3.5.

Also can be downloaded from github repo:

```bash
# Recommended to put fio inside different directory name as fio is also name of the binary
mkdir git_fio
cd git_fio

git clone https://github.com/axboe/fio

# You install additional libraries like zlib or rbd (librbd) before configure
cd fio

./configure

make && make install
```

### Python

Require Python3

## Usage: 

### Run Test:

```bash
python3 ./run_tests.py
```

### Clear Filesystem (remove dependencies)

```bash
python3 ./run_tests.py --clear
```

## Configuration:

FIO parameters are passed by configuration file 'test_config.ini'

Parameters can be provided as a list then automation will loop over them 
Currently supported list params:

```
- num_jobs 	: Number of FIO jobs
- file_suze 	: Size of each job file
- mix_read 	: Ratio of Read to Write (i.e 70 mean 70 Read 30 Writes)
- workload 	: Workload specification (from FIO)
```

## Output format:

Output from each file system is placed inside folder with name of FS, and 
subdirectory described by time that test was perform.
Every FIO performance (test loop iteration) collect output of fio inside file
called:

```
<test_name>_<workload_name>_<nr_jobs>_jb_<blk_size>_bl_<rw_ratio>_rw_<file_system>_<kernel_version>
```

During performance test also stats from different tools are collected inside
directory

```
stats_<workload_name>_<nr_jobs>_jobs_<blk_size>_<file_system>_<kernel_version>
```

## Backlog:
 - btrfs support
 - integration with gnuplot
 - support for perf