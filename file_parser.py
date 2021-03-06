import configparser
import functools


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass

    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass

    return False


class file_parser:
    FILE_VMSTAT = "FILE_VMSTAT"
    FILE_FIO_OUT = "FILE_FIO_OUT"
    CONFIG_NAME = "test_config.ini"
    config = None

    p_prefix = lambda s : s[s.find('(')+1:s.find(')')]
    p_sufix = lambda s : s[s.find(')')+1:]
    p_index = lambda s : file_parser.p_prefix(s).split('_')[0]
    p_name = lambda s: file_parser.p_prefix(s)[file_parser.p_prefix(s).find('_')+1:]
    p_filed_spec = lambda y : [y[:y.find(':')], y[y.find(':')+1:]]
    p_filed = lambda s : file_parser.p_filed_spec(file_parser.p_sufix(s))

    def __init__(self, config=None):
        if config is not None:
            self.config = config

    """ Simple class to parse files, currently support two types of files:
        - FILE_VMSTAT: output of vmstat
        - FILE_FIO_OUT: output of FIO
    """
    @staticmethod
    def my_compare(s1, s2):
        first = file_parser.p_index(s1)
        second = file_parser.p_index(s2)
        return int(first) - int(second)

    def parse(self, file_type: object, file: object) -> object:
        f = open(file, 'r', errors='replace')

        if file_type == file_parser.FILE_VMSTAT:
            # Skip first line in vmstat
            content = self.parse_file_array(f.readlines()[1:])
        elif file_type == file_parser.FILE_FIO_OUT:
            content = self.parse_file_sections(f)

        return content

    """ First line supposed to be dictionary entries
        Rest of the file numeric values in the columns
        If there is any non numeric data in the row, it will be skipped
        Return as a result dictionary of row_name:row_vaules
    """

    def parse_file_array(self, lines):
        res = {}
        title = lines[0].split()
        for i in title:
            res.update({i: []})

        for i in range(1, len(lines)):
            cols = lines[i].split()
            # in case of some stats if title is appended during work
            # skip non numeric or broken (shorter then title) rows
            if (i > 1 and not is_number(cols[0])) or (len(cols) < len(title)):
                continue
            for n in range(len(title)):
                res[title[n]].append(cols[n])

        return res

    """ Find sections inside structural file (fio output)
        Return dictionary {section_name -> section_rows}
    """

    @staticmethod
    def find_sections(rows, section):
        sec = []
        start = 0
        for r in rows:
            if section in r:
                start = 1
            if start == 1:
                if len(r) == 0 or r.isspace():
                    break
                sec.append(r)

        return sec

    @staticmethod
    def get_value(string):
        # if string inside brackets extract them
        # if '=' get only value
        return (lambda x: x[x.find('=') + 1:])(string.strip('()').strip(','))

    """ Get value from section: value position is described by pair[row, col (, args)]
        - row : can be string or number 
                describe either string pattern that open the target row or number
        - col : can be string or number
                describe position of the value in row (word number) or label i.e. 'bw='
        - args... : if args specified, field will be additionally split
                across arg[0], and arg[1] position will be returned
    """

    @staticmethod
    def get_field_from_section(section_rows, field):
        global result
        row = ''
        if len(field) < 2:
            raise ValueError('Invalid parameter: expected value pair!')

        # Find row:
        if is_number(field[0]):
            row = section_rows[field[0]]
        else:
            for r in section_rows:
                if field[0] in r:
                    row = r
                    break

        if len(row) == 0:
            raise ValueError('Row not found!')

        row = row.split()
        # Find field in the row:
        if is_number(field[1]):
            result = row[field[1]]
        else:
            for r in row:
                if field[1] in r:
                    result = file_parser.get_value(r)

        if len(field) > 2:
            result = result.split(field[2])[field[3]]

        return result

    """ Extract: 
            - Run status for all jobs (READ/WRITE)
            - Disk stats (read/write)
            
        # Not done yet:
            - stats per process
    """

    def parse_file_sections(self, file):
        rows = file.readlines()
        values = {}

        if self.config is None:
            self.config = configparser.ConfigParser()
            self.config.read(self.CONFIG_NAME )

        fio_output = self.config.get('csv_output', 'fio_output')
        fio_fields = fio_output.split(';')
        sorted(fio_fields, key=functools.cmp_to_key(self.my_compare))

        # TODO: Move this to the config file
        disk_stats_tag = 'Disk stats (read/write):'
        status_group_tag = 'Run status group'
        item_list1 = []

        # Field is described as a pair: row
        #        description = [[read_bw, write_bw],  [[1, 'ios', '/', 0], [1, 'ios', '/', 1]]]
        #        title = {status_group_tag: [read_bw[0], write_bw[0]], disk_stats_tag: [ios_r, ios_w]}
        # List of all items that need to be extracted from the file
        for it in fio_fields:
            ent = {'section': status_group_tag, 'title': file_parser.p_name(it), 'description': file_parser.p_filed(it)}
            item_list1.append(ent)

        for i in item_list1:
            # Find sections
            selected_section = file_parser.find_sections(rows, i['section'])

            if len(selected_section) == 0:
                print('It looks like given log file is broken: See raw content below:'.format(i['section']))
                raise AssertionError("Log file {} most likely broken!".format(file))

            # Find fields in sections
            values.update({i['title']: file_parser.get_field_from_section(selected_section, i['description'])})

        perf_header = 'Performance counter stats'
        perf_end = 'seconds time elapsed'
        # Get Perf Stats
        start = 0
        time = 0
        counters = []
        for s in rows:
            if perf_end in s:
                time = float(s.split()[0])
                break
            if perf_header in s or start == 1:
                start = 1
                if s.isspace():
                    continue
                else:
                    counters.append(s)
        if len(counters) > 0:
            del (counters[0])
            perf_cnt = {}
            for idx, v in enumerate(counters):
                val = int(v.split()[0].replace(",", ""))
                val /= time
                perf_cnt.update({idx: val})
            if len(perf_cnt) > 0:
                values.update({'perf_cnt': perf_cnt})

        return values


if __name__ == "__main__":
    print("TEST FIO output!")
    parser = file_parser()
    res = parser.parse(file_parser.FILE_FIO_OUT, "./examples/fio_reference_output.log")
    print(res)

    print("TEST vmstat output!")
    parser = file_parser()
    res = parser.parse(file_parser.FILE_VMSTAT, "./examples/vmstat")
    print(res)
