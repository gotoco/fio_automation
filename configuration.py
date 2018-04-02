import configparser
from importlib import import_module


def extract_man_field(config, section, fname):
    try:
        val = config.get(section, fname)
    except configparser.NoOptionError as ex:
        print('Error during configuration parsing!\nMandatory field: {} in section {} missing:\n{}'
              .format(section, fname, ex))
        return
    # We treat all inputs with pattern {$XXX.YY} 
    # notice some of FIO variable can be used as a $XXX so we allow them
    # value is a python script
    if val.startswith('${') and val.endswith('}') and '.' in val:
        name = val.strip('$').strip('{}')
        p, m = name.rsplit('.', 1)

        mod = import_module(p)
        met = getattr(mod, m)
        return met()

    return val


def extract_opt_field(config, section, fname):
    try:
        val = config.get(section, fname)
    except configparser.NoOptionError as ex:
        return None

    return val


def get_fslist(config):
    return extract_man_field(config, 'test', 'fs2test').split(',')
