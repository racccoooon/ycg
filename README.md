# yaml-config-generator (ycg)
ycg merges and templates yaml files.

```
$ ycg -h
usage: ycg [-h] [-o FILE] [-d FILE] [-V KEY VALUE] [-b DIR] [--version] FILE [FILE ...]

yaml config generator

positional arguments:
  FILE                  input files (use '-' for stdin)

options:
  -h, --help            show this help message and exit
  -o FILE, --output FILE
                        output to this file (default is stdout)
  -d FILE, --data FILE  data files (use '-' for stdin)
  -V KEY VALUE, --var KEY VALUE
                        add a variable that can be used in templates
  -b DIR, --basedir DIR
                        base directory for resolving paths in stdin input (ignored for files, defaults to current working directory)
  --version             show program's version number and exit
```

## Installation

Install from PyPI with `pip install ycg` or just download the ycg.py file (make sure you have pyyaml and jinja2 installed).

```bash
$ curl -o ycg.py https://raw.githubusercontent.com/racccoooon/ycg/refs/heads/main/src/ycg.py
$ chmod +x ycg.py
# install to /usr/local/bin
$ sudo mv ycg.py /usr/local/bin/ycg
# or install to your local bin dir
$ mv ycg.py ~/.local/bin/ycg
```


## Merging
If multiple input files are specified they will be merged together.
Use `-` as the filename to read from stdin.

Files are merged in the order they are specified: The second file is merged into the first, then the third into the result of that and so on.

By default, lists are concatenated and mappings/dictionaries are combined.
If a value uses the `!overwrite` tag it will replace the existing value rather than merging with it.
Lists of mappings can use the `!merge_by:<key>` tag to specify a key by which to identify items.
Items with the same key will be merged, rather than preserving both values.

### Example `!merge_by:<key>`

```yaml
# file1.yml
users: 
  - {id: 1, name: "Foo"}
  - {id: 2, name: "Bar"}
```

```yaml
# file2.yml
users: !merge_by:id
  - {id: 1, email: "foo@example.com"}
  - {id: 3, name: "Bar"}
```

```
$ ycg file1.yml file2.yml
```

```yaml
# result
users:
  - {id: 1, name: "Foo", email: "foo@example.com"}
  - {id: 2, name: "Bar"}
  - {id: 3, name: "Bar"}
```



### Example `!overwrite`

```yaml
# file1.yml
numbers: [1, 2, 3, 4]
words: ["foo", "bar", "qux"]
```

```yaml
# file2.yml
numbers: !overwrite [2, 3, 5, 7]
words: ["foo", "foobar", "bar"]
```

```
$ ycg file1.yml file2.yml
```

```yaml
# output
numbers: [2, 3, 5, 7]
words: ["foo", "bar", "qux", "foo", "foobar", "bar"]
```


## Inclusion

Other files can be included using `!include` (as a string value) or `!include:yaml` (as yaml data).

The value after the tag must be a string and specifies the path of the file to include.
Paths are always relative to the file in which they are specified.
Paths in stdin are relative to the current working directory, this can be overridden with the `--basedir` option.

Included yaml files can also use the same tags for inclusion, merging and templating.

### Example
```yaml
# input.yml
string_value: !include lorem.txt
yaml_value: !include:yaml lorem.yml
```

```yaml
# lorem.txt
Lorem Ipsum Dolor Sit Amet
```

```yaml
# lorem.yml
Lorem: Ipsum
Dolor: Sit Amet
```

```
$ ycg input.yml
```

```yaml
# output
string_value: Lorem Ipsum Dolor Sit Amet
yaml_value:
  Lorem: Ipsum
  Dolor: Sit Amet
```

## Templating
The tags `!template` and `!include:template` can be used to template strings or included files with jinja2.

Data for the templates can be specified as files (with the `--data` option) or as individual variables (with the `--var` option).
Use `-` as a data file to use stdin.
If multiple data files are specified they are merged together just like the input files, and can use the same tags except for `!template` and `!include:template`.

### Example

```yaml
# input.yml
hello: !template "Hello {{ name }}"
numbers: !include:template template.j2

```

```yaml
# data1.yml
numbers: [1, 2]
```

```yaml
# data2.yml
numbers: [3, 4]
```

```text
{# template.j2 #}
{% for x in numbers %}
Number {{ x }}
{% endfor %}
```

```
$ ycg -d data1.yml -d data2.yml -V name World input.yml
```

```yaml
# output
hello: Hello World
numbers: |
    Number 1
    Number 2
    Number 3
    Number 4
```