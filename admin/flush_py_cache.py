#!/usr/bin/env python

import fnmatch
import os
import sys


def get_valid_pyc_files():
    for root, dir_names, file_names in os.walk("."):
        for file_name in fnmatch.filter(file_names, '*.pyc'):
            pyc_file_path = os.path.join(root, file_name)
            py_file_path = pyc_file_path[:-1]

            if os.path.isfile(py_file_path):
                yield pyc_file_path


def main():
    for pyc_file_path in get_valid_pyc_files():
        print( 'removing', pyc_file_path)
        os.remove(pyc_file_path)


if __name__ == '__main__':
    main()
