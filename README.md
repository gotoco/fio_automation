# Simple Python Wrapper around FIO to perform automation

This simple wrapper runs FIO tests for 3 file systems 
and give results that can be easly comparable.
Currently 3 FS that are supported: xfs, ext4 and zfs.

## Requirements:

### FIO

Compatible (and tested) with fio 3.5.

Also can be downloaded from github repo:

```bash
git clone https://github.com/axboe/fio

# You install additional libraries like zlib or and 
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
<workload_name>_<nr_jobs>_jobs_<blk_size>_<file_system>_<kernel_version>
```

During performance test also stats from different tools are collected inside
directory

```
stats_<workload_name>_<nr_jobs>_jobs_<blk_size>_<file_system>_<kernel_version>
```
