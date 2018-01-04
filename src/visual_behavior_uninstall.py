import os
import shutil
import pip


def main():
    shutil.rmtree(os.path.expanduser('~') + '/visual_behavior', ignore_errors=True)
    pip.main(["uninstall", 'visual_behavior'])
    os.remove(os.path.expanduser('~') + '/Desktop/visual_behavior.lnk')


if __name__ == '__main__':
    main()
