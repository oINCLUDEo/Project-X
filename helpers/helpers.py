import os


def remove_file(filenames_list):
    if type(filenames_list) is list:
        for filename in filenames_list:
            os.remove(filename)
    elif type(filenames_list) is str:
        os.remove(filenames_list)
