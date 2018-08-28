#!/usr/bin/env python
import sys
import xml.etree.ElementTree as ET
import re
import os.path

# branch-rate="0.0" complexity="0.0" line-rate="1.0"
# branch="true" hits="1" number="86"

def find_lines(j_package, filename):
    """Return all <line> elements for a given source file in a package."""
    lines = list()
    sourcefiles = j_package.findall("sourcefile")
    for sourcefile in sourcefiles:
        if sourcefile.attrib.get("name") == os.path.basename(filename):
            lines = lines + sourcefile.findall("line")
    return lines

def line_is_after(jm, start_line):
    return int(jm.attrib.get('line', 0)) > start_line

def method_lines(jmethod, jmethods, jlines):
    """Filter the lines from the given set of jlines that apply to the given jmethod."""
    start_line = int(jmethod.attrib.get('line', 0))
    larger     = list(int(jm.attrib.get('line', 0)) for jm in jmethods if line_is_after(jm, start_line))
    end_line   = min(larger) if len(larger) else 99999999

    for jline in jlines:
        if start_line <= int(jline.attrib['nr']) < end_line:
            yield jline

def convert_lines(j_lines, into):
    """Convert the JaCoCo <line> elements into Cobertura <line> elements, add them under the given element."""
    c_lines = ET.SubElement(into, 'lines')
    for jline in j_lines:
        mb = int(jline.attrib['mb'])
        cb = int(jline.attrib['cb'])
        ci = int(jline.attrib['ci'])

        cline = ET.SubElement(c_lines, 'line')
        cline.set('number', jline.attrib['nr'])
        cline.set('hits', '1' if ci > 0 else '0') # Probably not true but no way to know from JaCoCo XML file

        if mb + cb > 0:
            percentage = str(int(100 * (float(cb) / (float(cb) + float(mb))))) + '%'
            cline.set('branch',             'true')
            cline.set('condition-coverage', percentage + ' (' + str(cb) + '/' + str(cb + mb) + ')')

            cond = ET.SubElement(ET.SubElement(cline, 'conditions'), 'condition')
            cond.set('number',   '0')
            cond.set('type',     'jump')
            cond.set('coverage', percentage)
        else:
            cline.set('branch', 'false')

def guess_filename(path_to_class):
    m = re.match('([^$]*)', path_to_class)
    return (m.group(1) if m else path_to_class) + '.java'

def add_counters(source, target, version=None):
    target.set('line-rate',   counter(source, 'LINE', operation=fraction))
    target.set('branch-rate', counter(source, 'BRANCH', operation=fraction))
    target.set('complexity', counter(source, 'COMPLEXITY', operation=sum))
    if version:
        target.set('version', version)
        for t_key, s_key in (
                                ('lines', 'LINE'),
                                ('branches', 'BRANCH'),
                                ('instructions', 'INSTRUCTION'),
                                ('classes', 'CLASS'),
                                ('methods', 'METHOD')
        ):
            target.set(
                '{}-covered'.format(t_key),
                counter(source, s_key, operation=None, value='covered')
            )
            target.set(
                '{}-valid'.format(t_key),
                counter(source, s_key, operation=None, value='valid')
            )

def fraction(covered, missed):
    return covered / (covered + missed)

def sum(covered, missed):
    return covered + missed

def counter(source, type_, operation=fraction, value=None):
    cs = source.findall('counter')
    c = next((ct for ct in cs if ct.attrib.get('type') == type_), None)
    typecast = int if value else float
    if c is not None:
        covered = typecast(c.attrib['covered'])
        missed  = typecast(c.attrib['missed'])
        all_ = covered + missed
        values = {'valid': all_, 'covered': covered}

        return str(values[value]) if operation is None else str(operation(covered, missed))
    else:
        return '0' if operation is None else '0.0'


def convert_method(j_method, j_lines):
    c_method = ET.Element('method')
    c_method.set('name',      j_method.attrib['name'])
    c_method.set('signature', j_method.attrib['desc'])

    add_counters(j_method, c_method)
    convert_lines(j_lines, c_method)

    return c_method

def convert_class(j_class, j_package):
    c_class = ET.Element('class')
    c_class.set('name',     j_class.attrib['name'].replace('/', '.'))
    c_class.set('filename', guess_filename(j_class.attrib['name']))

    all_j_lines = list(find_lines(j_package, c_class.attrib['filename']))

    c_methods   = ET.SubElement(c_class, 'methods')
    all_j_methods = list(j_class.findall('method'))
    for j_method in all_j_methods:
        j_method_lines = method_lines(j_method, all_j_methods, all_j_lines)
        c_methods.append(convert_method(j_method, j_method_lines))

    add_counters(j_class, c_class)
    convert_lines(all_j_lines, c_class)

    return c_class

def convert_package(j_package):
    c_package = ET.Element('package')
    c_package.attrib['name'] = j_package.attrib['name'].replace('/', '.')

    c_classes = ET.SubElement(c_package, 'classes')
    for j_class in j_package.findall('class'):
        c_classes.append(convert_class(j_class, j_package))

    add_counters(j_package, c_package)

    return c_package

def convert_root(source, target, source_roots, version):
    target.set('timestamp', str(int(source.find('sessioninfo').attrib['start']) / 1000))

    sources     = ET.SubElement(target, 'sources')
    for s in source_roots:
        ET.SubElement(sources, 'source').text = s

    packages = ET.SubElement(target, 'packages')
    for package in source.findall('package'):
        packages.append(convert_package(package))

    add_counters(source, target, version)

def jacoco2cobertura(filename, source_roots, version):
    if filename == '-':
        root = ET.fromstring(sys.stdin.read())
    else:
        tree = ET.parse(filename)
        root = tree.getroot()

    into = ET.Element('coverage')
    convert_root(root, into, source_roots, version)
    print '<?xml version="1.0" ?>'
    print ET.tostring(into)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print "Usage: cover2cover.py FILENAME VERSION [SOURCE_ROOTS]"
        sys.exit(1)

    filename = sys.argv[1]
    version = sys.argv[2]
    source_roots = sys.argv[3:] if 3 < len(sys.argv) else '.'

    jacoco2cobertura(filename, source_roots, version)
