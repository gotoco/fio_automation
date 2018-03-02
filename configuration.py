import configparser


def extract_man_field(config, section, fname):
    try:
        val = config.get(section, fname)
    except configparser.NoOptionError as ex:
        print('Error during configuration parsing!\nMandatory field: {} in section {} missing:\n{}'
              .format(section, fname, ex))
        return

    return val


def get_fslist(config):
    return extract_man_field(config, 'test', 'fs2test').split(',')
