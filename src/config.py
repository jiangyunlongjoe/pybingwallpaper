#!/usr/bin/env python3
import log
import argparse
import sys
from argparse import Namespace

_logger = log.getChild('config')

class ConfigParameter:
    ''' 
        ConfigParameter is an abstract of configuration data which integrate config file
        and commandline-like argument data models.
    '''
    def __init__(self, name, defaults=None, type=None, choices=None, help='', loader_srcs=None, loader_opts=None):
        '''
        name        - name of option.
        defaults    - default values which can be specified as a dict with keys 
                    specify different default values of corresponding platform,
                    e.g. {'win32': True, 'linux': False, 'darwin': False, '*': True}
                    name of platforms are defined as in sys.platform and '*' stands for
                    unspecified platforms which is equivalent to assigning value directly
                    to defaults. That is, 'default=1' works same as 'default={'*':1}'
        type        - the type to which the parameter should be converted, e.g.
                    "type=int" employes int() on loaded values by loader.
        choices     - a container of the allowable values for the parameter. a
                    ValueError will be raised if type converted value not a member of
                    not-none choices container
        help        - human readable message describe meaning of this parameter
        loader_srcs - supported sources from which this parameter could be loaded
                      'all' is a reserved name for all known loader sources;
                      other source names are decided by certain loaders
        loader_opts - options specified as dict will be used by certain loaders
                      read document of loaders for available options
        '''
        self.name = str(name)
        self.validate_name()
        self.defaults = defaults if isinstance(defaults, dict) else {'*': defaults}
        if type is not None: self.type = type
        if choices is not None: self.choices = choices
        self.help = help
        self.loader_opts = loader_opts if loader_opts is not None else dict()
        self.loader_srcs = loader_srcs if loader_srcs is not None else ['all']

    def validate_name(self):
        if any(map(lambda x:x.isspace(), self.name)):
            raise ValueError("parameter name can't contain space")

    def get_default(self, platform=None):
        if not platform:
            platform = sys.platform
        if platform not in self.defaults:
            platform = '*'
        return self.defaults[platform]

    def get_option(self, loader_key, option_name, default=None):
        opts = self.loader_opts.get(loader_key, dict())
        if option_name in opts:
            return opts[option_name]
        else:
            return default

    def support_loader(self, loader_name):
        return 'all' in self.loader_srcs or loader_name in self.loader_srcs

    def type_cast(self, value):
        if hasattr(self, 'type'):
            return self.type(value)
        return value

    def __repr__(self):
        return '''{}(name={}, defaults={}, type={}, choices={}, help={}, loader_opts={})'''.format(
                        self.__class__.__name__,
                        repr(self.name),
                        repr(self.defaults),
                        repr(self.type if hasattr(self, 'type') else None),
                        repr(self.choices if hasattr(self, 'choices') else None),
                        repr(self.help),
                        repr(self.loader_opts)
                    )

    def __eq__(self, other):
        return self.name == other.name

class ConfigDatabase:
    def __init__(self, prog, description = None, parameters = None):
        self.prog = prog
        self.description = description
        self.parameters = list(parameters) if parameters is not None else list()

    def add_param(self, param):
        if param not in self.parameters:
            self.parameters.append(param)
        else:
            raise NameError('duplicated parameter name "%s" found'%(param.name,))

    def __repr__(self):
        return '{}(prog={}, description={}, parameters={})'.format(
                    self.__class__.__name__,
                    repr(self.prog),
                    repr(self.description),
                    repr(self.parameters)
                )

class ConfigLoader:
    def load(self, db, generate_default=False, *args, **kwargs):
        raise NotImplemented()

class ConfigDumper:
    def dump(self, db, conf, buf, *args, **kwargs):
        raise NotImplemented()

from configparser import ConfigParser
class ConfigFileLoader(ConfigLoader):
    '''
    Options keyword: 'conffile'
    Supported options can be set in ConfigParameter: 
        section - under which section this value is saved 
                  use the DEFAULT section if not specified
        key     - with what name this value is saved
        converter 
                - a callable which converts string to desired object
                  use type_cast of parameter if not specified
    Ref:
        http://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    '''
    OPT_KEY = 'conffile'

    def load_value(self, param, parser, ans, generate_default):
        section = param.get_option(self.OPT_KEY, 'section', None)
        if section is None: section = parser.default_section
        key = param.get_option(self.OPT_KEY, 'key', param.name)
        converter = param.get_option(self.OPT_KEY, 'converter', param.type_cast)

        if parser.has_option(section, key):
            value = parser.get(section, key)
            loaded = True
        elif generate_default:
            value = param.get_default()
            loaded = True
        else:
            value = None
            loaded = False
        if loaded: value = converter(value)
        return loaded, key, value

    def load(self, db, data, generate_default=False):
        ans = Namespace()
        parser = ConfigParser()
        parser.read_file(data)
        for param in db.parameters:
            if not param.support_loader(self.OPT_KEY): continue
            loaded, key, value = \
                self.load_value(param, parser, ans, generate_default)
            if loaded:
                setattr(ans, key, value)
        return ans

class ConfigFileDumper(ConfigDumper):
    '''
    Options keyword: 'conffile'
    Supported options can be set in ConfigParameter: 
        section - under which section this value is saved 
                  use the DEFAULT section if not specified
        key     - with what name this value is saved.
                  use the name of parameter if not given
        formatter
                - a callable which converts value to string
                  use built-in str() if not specified
    Ref:
        http://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    '''
    OPT_KEY = 'conffile'

    def get_param_by_name(self, db, name):
        key_comparator = lambda param: \
                name == param.get_option(self.OPT_KEY, 'key', None)
        name_comparator = lambda param: name == param.name
        by_key = list(filter(key_comparator, db.parameters))
        if len(by_key) > 1:
            raise ValueError('More than one parameters are set with name {}'.format(name))
        elif len(by_key) == 1:
            return by_key[0]

        by_name = list(filter(name_comparator, db.parameters))
        if len(by_name) > 1:
            raise ValueError('More than one parameters are set with key {}'.format(name))
        elif len(by_name) == 1:
            return by_name[0]
        else:
            return None

    def dump(self, db, conf, buf, *args, **kwargs):
        parser = ConfigParser()
        for k, v in vars(conf).items():
            param = self.get_param_by_name(db, k)
            if param is None:
                _logger.warn('ignore an unknown config %s=%s', k, v)
            section = param.get_option(self.OPT_KEY, 'section', parser.default_section)
            if section != parser.default_section and \
                    not parser.has_section(section): 
                parser.add_section(section)
            formatter = param.get_option(self.OPT_KEY, 'formatter', str)
            parser.set(section, k, formatter(v))
        parser.write(buf, kwargs.get('space_around_delimiters', True))


class CommandLineArgumentsLoader(ConfigLoader):
    '''
    Options keyword: 'cli'
    Supported options can be set in ConfigParameter: 
        flags - container which will be converted to CLI option flags
        other options can be found here 
            http://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    '''
    OPT_KEY = 'cli'

    @staticmethod
    def param_to_arg_opts(param, generate_default):
        # load common options
        opts = {
                'help': param.help,
                'dest': param.name,
            }
        if hasattr(param, 'type'): opts['type'] = param.type
        if hasattr(param, 'choices'): opts['choices'] = param.choices

        if generate_default:
            opts['default'] = param.get_default()
        
        # load specific options at last so that
        # specific ones take higher priority in case a same
        # key occurs in both common part and loader_opts part
        specific_opts = param.loader_opts.get(CommandLineArgumentsLoader.OPT_KEY, dict())
        opts.update(specific_opts)
        if 'flags' in opts: del(opts['flags'])
        return opts

    @staticmethod
    def param_to_arg_flags(param):
        opts = param.loader_opts.get(CommandLineArgumentsLoader.OPT_KEY, dict())
        if 'flags' in opts:
            ans = opts['flags']
        elif len(param.name) == 1:
            # simple name like 'a' will be converted to '-a'
            ans = ['-'+param.name,]
        else:
            # long name like 'debug' will be converted to '--debug'
            ans = ['--'+param.name,]
        return ans

    @staticmethod
    def assemble_parser(db, generate_default):
        parser = argparse.ArgumentParser(prog = db.prog, description = db.description)
        for param in db.parameters:
            if not param.support_loader(CommandLineArgumentsLoader.OPT_KEY): continue
            parser.add_argument(
                    *CommandLineArgumentsLoader.param_to_arg_flags(param), 
                    **CommandLineArgumentsLoader.param_to_arg_opts(param, generate_default)
            )
        return parser

    def load(self, db, data, generate_default=False):
        parser = CommandLineArgumentsLoader.assemble_parser(db, generate_default)
        return parser.parse_args(data)

class DefaultValueLoader(ConfigLoader):
    OPT_KEY = 'defload'

    def __init__(self, platform=None):
        self.platform = platform

    def load(self, db, data=None, generate_default=True):
        ans = Namespace()
        if not generate_default: return ans
        for param in db.parameters:
            val = param.get_default(self.platform)
            val = param.type(val) if hasattr(param, 'type') else val
            setattr(ans, param.name, val)
        return ans
