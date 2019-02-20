import os
import shutil
import sys
import tarfile
import zipfile

import requests
from PyQt5.QtCore import QThread
from PyQt5.QtCore import pyqtSignal

from hpxqt import consts as hpxqt_consts

if getattr(sys, 'frozen', False):
    FOLDER = os.path.dirname(os.path.abspath(sys.argv[0]))
elif __file__:
    FOLDER = os.path.dirname(__file__)


class DownloadThread(QThread):
    signal_download_finished = pyqtSignal(int)

    def __init__(self, url, file_path):
        QThread.__init__(self)
        self.url = url
        self.download_path = file_path

    def __del__(self):
        self.wait()

    def run(self):
        # TODO: add proxy for download?
        response = requests.get(self.url, stream=True)
        if response.status_code != 200:
            return

        with open(self.download_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if not chunk:
                    continue
                f.write(chunk)
        self.signal_download_finished.emit(hpxqt_consts.FINISHED_DOWNLOAD)


class WindowUpdateMixIn(object):
    signal_upgrade_status_change = pyqtSignal(int)

    def __init__(self):
        self.download_thread = None
        self.last_update = None
        self.download_name = None
        self.download_folder = FOLDER
        self.download_path = None

        self.signal_upgrade_status_change.connect(self.upgrade_status_change)

    def start_upgrade(self):
        self.last_update = self.router.db_manager.last_update()
        self.download_name = self.last_update.url.rsplit('/', maxsplit=1)[1]
        
        if self.last_update.platform == hpxqt_consts.MAC_OS:
            self.download_folder = os.path.dirname(os.path.dirname(os.path.dirname(FOLDER)))
        
        self.download_path = os.path.join(self.download_folder, self.download_name)
            
        if self.last_update.is_downloaded:
            self.signal_upgrade_status_change.emit(hpxqt_consts.START_INSTALL)
            return

        self.signal_upgrade_status_change.emit(hpxqt_consts.START_DOWNLOAD)
        self.download_thread = DownloadThread(self.last_update.url,
                                              self.download_path)
        self.download_thread.signal_download_finished.connect(
            self.upgrade_status_change)
        self.download_thread.start()

    def upgrade_status_change(self, kind):
        if kind == hpxqt_consts.FINISHED_DOWNLOAD:
            self.router.db_manager.mark_downloaded(self.last_update.version)

        if kind in [hpxqt_consts.START_INSTALL, hpxqt_consts.FINISHED_DOWNLOAD]:
            self.process_installation()
    
    def process_compressed_linux(self):
        with tarfile.open(self.download_path) as tar:
            tar_content = tar.getnames()
            tar.extractall()

        # Get path to executable
        src_dir = os.path.join(self.download_folder, tar_content[-1])
        # Must provide full path, otherwise executable won't be replaced!
        dest_dir = os.path.join(self.download_folder,
                                hpxqt_consts.LINUX_APP_NAME)
        shutil.move(src_dir, dest_dir)
        shutil.rmtree(tar_content[0])

    def process_compressed_osx(self):
        with zipfile.ZipFile(self.download_path) as zip:
            # Extract top .app directory
            zip.extractall()
        
    def process_installation(self):
        """
        Updates database and replaces a current process with
        a new process.
        """
        platform = self.last_update.platform
        if platform in hpxqt_consts.COMPRESSED_FILE_OS:
            getattr(self, 'process_compressed_%s' % platform)()
            os.remove(self.download_path)

        self.router.db_manager.remove_downloaded(self.last_update.version)
        self.router.db_manager.mark_installed(self.last_update.version)
        self.signal_upgrade_status_change.emit(hpxqt_consts.FINISHED_INSTALL)
