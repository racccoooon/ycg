#!/usr/bin/env python3

import typing
import yaml
from pathlib import Path
import sys
import argparse
import os
from jinja2 import Template


def filepath_type(must_exist=False, parent_must_exist=False):
    def _type(val):
        if val == '-':
            return '-'

        filepath = Path(val).resolve()

        if must_exist and not filepath.exists():
            msg = f'File not found: {filepath}'
            raise argparse.ArgumentTypeError(msg)

        if parent_must_exist and not filepath.parent.exists():
            msg = f'Directory not found: {filepath.parent}'
            raise argparse.ArgumentTypeError(msg)

        return filepath

    return _type


def render_template(template: str, template_data) -> str:
    return Template(template).render(**template_data)


class OverwriteNode:
    def __init__(self, value):
        self.value = value


class MergeByNode:
    def __init__(self, value, merge_by):
        self.value = value
        self.merge_by = merge_by


class Reader:
    def __init__(self, source: typing.Union[Path,  typing.TextIO], basedir: Path, enable_templating: bool, template_data: dict):
        self.source = source
        self.loader = yaml.SafeLoader
        self.enable_templating = enable_templating
        self.template_data = template_data
        self.basedir = basedir
        self.loader.add_constructor("!include", lambda _, n: self.include(n))
        self.loader.add_constructor("!include:yaml", lambda _, n: self.include_yaml(n))
        self.loader.add_constructor("!overwrite", lambda l, n: self.overwrite(l, n))
        self.loader.add_multi_constructor("!merge_by:", lambda l, s, n: self.merge_by(l, s, n))

        if enable_templating:
            self.loader.add_constructor("!template", lambda _, n: self.template(n))
            self.loader.add_constructor("!include:template", lambda _, n: self.include_template(n))

    def read(self):
        if isinstance(self.source, Path):
            with self.source.open() as f:
                return yaml.load(f, Loader=self.loader)
        else:
            return yaml.load(self.source, Loader=self.loader)

    def dir(self):
        if isinstance(self.source, Path):
            return self.source.parent
        else:
            return self.basedir

    def template(self, node: yaml.nodes.Node) -> str:
        if not isinstance(node.value, str):
            raise ValueError('!template requires a string value')
        return render_template(node.value, self.template_data)

    def include(self, node: yaml.nodes.Node) -> str:
        if not isinstance(node.value, str):
            raise ValueError('!include requires a string value')
        path = self.dir() / node.value
        return path.read_text()

    def include_template(self, node: yaml.nodes.Node) -> str:
        if not isinstance(node.value, str):
            raise ValueError('!include:template requires a string value')
        path = self.dir() / node.value
        return render_template(path.read_text(), self.template_data)

    def include_yaml(self, node: yaml.nodes.Node):
        if not isinstance(node.value, str):
            raise ValueError('!include:yaml requires a string value')
        path = self.dir() / node.value
        return Reader(path, self.basedir, enable_templating=self.enable_templating,
                      template_data=self.template_data).read()

    @staticmethod
    def overwrite(loader: yaml.SafeLoader, node):
        if isinstance(node, yaml.nodes.SequenceNode):
            value = loader.construct_sequence(node)
        elif isinstance(node, yaml.nodes.MappingNode):
            value = loader.construct_mapping(node)
        elif isinstance(node, yaml.nodes.ScalarNode):
            value = node.value
        else:
            raise ValueError(f'invalid node type: {node.id}')
        return OverwriteNode(value)

    @staticmethod
    def merge_by(loader: yaml.SafeLoader, suffix: str, node):
        if isinstance(node, yaml.nodes.SequenceNode):
            val = loader.construct_sequence(node)
        else:
            raise ValueError(f'!merge_by is only valid on sequence nodes, got {node.id}')

        return MergeByNode(val, suffix)


def unwrap(val):
    if isinstance(val, OverwriteNode) or isinstance(val, MergeByNode):
        return val.value
    if isinstance(val, list):
        return [unwrap(x) for x in val]
    if isinstance(val, dict):
        return {
            k: unwrap(v)
            for k, v in val.items()
        }
    return val


def merge_value(a, b):
    if isinstance(b, OverwriteNode):
        return b.value
    elif isinstance(a, list) and isinstance(b, list):
        return [*a, *(unwrap(x) for x in b)]
    elif isinstance(a, list) and isinstance(b, MergeByNode):
        assert isinstance(b.value, list)
        merge_by = b.merge_by
        b = b.value
        result = [*a]
        for v in b:
            if isinstance(v, dict) and merge_by in v:
                key = v[merge_by]
            elif isinstance(v, OverwriteNode) and isinstance(v.value, dict) and merge_by in v.value:
                key = v.value[merge_by]
            else:
                key = None

            if key is not None:
                idx = next(
                    (i for i, x in enumerate(result) if isinstance(x, dict) and merge_by in x and x[merge_by] == key),
                    None)
                if idx is not None:
                    result[idx] = merge_value(result[idx], v)
                else:
                    result.append(unwrap(v))
            else:
                result.append(unwrap(v))
        return result

    elif isinstance(a, dict) and isinstance(b, dict):
        result = {**a}
        for k, v in b.items():
            if k in result:
                if isinstance(v, OverwriteNode):
                    result[k] = v.value
                else:
                    result[k] = merge_value(result[k], v)
            else:
                result[k] = unwrap(v)
        return result
    else:
        return b


def read_and_merge_files(files, basedir, enable_templating=False, template_data=None):
    result = {}

    for input_file in files:
        if input_file == '-':
            input_file = sys.stdin
        layer = Reader(input_file, basedir, enable_templating=enable_templating, template_data=template_data).read()
        result = merge_value(result, layer)

    return result


def getenv(name, default=None):
    val = os.environ.get(name, default)
    if val is None:
        return ''
    return val


def main():
    parser = argparse.ArgumentParser(prog='ycg', description='yaml config generator')

    parser.add_argument('input_files', nargs='+', default=[], type=filepath_type(must_exist=True), metavar='FILE',
                        help='input files (use \'-\' for stdin)')
    parser.add_argument('-o', '--output', dest='output_file', metavar='FILE', default='-',
                        type=filepath_type(parent_must_exist=True),
                        help='output to this file (default is stdout)')
    parser.add_argument('-d', '--data', action='append', help='data files (use \'-\' for stdin)', dest='data_files',
                        default=[], type=filepath_type(must_exist=True), metavar='FILE')
    parser.add_argument('-V', '--var', nargs=2, action='append', help='add a variable that can be used in templates',
                        dest='vars', default=[], metavar=('KEY', 'VALUE'))
    parser.add_argument('-b', '--basedir',
                        help='base directory for resolving paths in stdin input (ignored for files, defaults to current working directory)',
                        dest='basedir', metavar='DIR', default=Path.cwd())
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')

    args = parser.parse_args()

    template_data = read_and_merge_files(args.data_files, args.basedir)

    for key, value in args.vars:
        template_data[key] = value

    if 'getenv' in template_data:
        print('warning: you are trying to define a data key \'getenv\' which is reserved', file=sys.stderr)

    template_data['getenv'] = getenv

    yaml_result = read_and_merge_files(args.input_files, args.basedir, enable_templating=True,
                                       template_data=template_data)

    if args.output_file == '-':
        print(yaml.safe_dump(yaml_result, sort_keys=False))
    else:
        with args.output_file.open('w') as file:
            yaml.safe_dump(yaml_result, file, sort_keys=False)


if __name__ == "__main__":
    main()
