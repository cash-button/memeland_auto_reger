from sys import platform
from os import system


class WindowName:
    def __init__(self, accs_amount: int):
        self.accs_amount = accs_amount
        self.accs_done = 0
        self.update_name()


    def update_name(self):
        if platform in ["windows", "win32"]:
            system(f'title MEME Soft [{self.accs_done}/{self.accs_amount}]')


    def update_accs(self):
        self.accs_done += 1
        self.update_name()
