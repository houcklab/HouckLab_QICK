import json
import os
import re

from PyQt5.QtWidgets import QWidget, QGridLayout, QPushButton, QComboBox, QLineEdit, QVBoxLayout, QLabel, QFormLayout


class AccountTabWidget(QWidget):

    def __init__(self, parent):
        super().__init__(parent=parent)

        self.currentAccount = 'default'

        self.lakeRootDir = os.getcwd()
        self.configDir = os.path.join(self.lakeRootDir, 'config')
        self.acccountDir = os.path.join(self.configDir, 'accounts')

        self.__loadAccount()

        self.__intiUI()

    def __intiUI(self):

        accountTabLayout = QGridLayout(self)

        self.__createAccountSettingsWidget(self)

        spacerWidget = QWidget(self)
        accountTabLayout.addWidget(spacerWidget, 1, 1)

        # saving and loading accounts
        saveLoadAccountWidget = QWidget(self)
        accountTabLayout.addWidget(saveLoadAccountWidget, 0, 1)

        saveLoadAccountLayout = QGridLayout(saveLoadAccountWidget)


        # load account button
        loadAccountButton = QPushButton('Load account')
        saveLoadAccountLayout.addWidget(loadAccountButton, 0, 0)

        accountDropDown = QComboBox(saveLoadAccountWidget)
        saveLoadAccountLayout.addWidget(accountDropDown, 0, 1)

        # find all possible accounts
        accountFileRegex = re.compile('(?P<accountName>.*).json')

        accountNames = []

        for root, dirs, files in os.walk(self.acccountDir):
            print(files)
            for file in files:
                match = accountFileRegex.search(file)
                accountNames.append(match.groupdict()['accountName'])

        for accountName in accountNames:
            accountDropDown.addItem(accountName)


        # save account button

        saveAccountButton = QPushButton('Save account')
        saveLoadAccountLayout.addWidget(saveAccountButton, 1, 0)

        saveAsAccountButton = QPushButton('Save as new account')
        saveLoadAccountLayout.addWidget(saveAsAccountButton, 2, 0)

        newAccountTextInput = QLineEdit(f'{self.currentAccount} copy', saveLoadAccountWidget)
        saveLoadAccountLayout.addWidget(newAccountTextInput, 2, 1)

    def __createAccountSettingsWidget(self, accountTab):

        # widget to dislay account details
        accountSettingsWidget = QWidget(parent=accountTab)

        accountDetailsLayout = QVBoxLayout(accountSettingsWidget)

        currentAccountLabel = QLabel(f'Current Account: {self.currentAccount}', accountSettingsWidget)

        accountDetailsLayout.addWidget(currentAccountLabel)

        accountSettingsFormWidget = QWidget(parent=accountSettingsWidget)
        accountDetailsLayout.addWidget(accountSettingsFormWidget)


        accountDetailsFormlayout = QFormLayout(accountSettingsFormWidget)
        # accountDetailsLayout.setHorizontalSpacing(100)
        # accountDetailsLayout.addWidget(currentAccountLabel, 0, 1)
        # accountDetailsLayout.addWidget(currentAccountName, 0, 2)

        # labels = []
        # values = []

        # display account details
        for key, value in self.accountSettings.items():
            if not key == 'account':
                textInput = QLineEdit(f'{value}')
                textInput.setFixedWidth(100)

                accountDetailsFormlayout.addRow(key, textInput)

        # for i in range(len(labels)):
        #     accountDetailsLayout.addWidget(labels[i], i + 1, 1)
        #     accountDetailsLayout.addWidget(values[i], i + 1, 2)

        accountTabLayout = accountTab.layout()
        accountTabLayout.addWidget(accountSettingsWidget, 0, 0)

    def __loadAccount(self):

        accountFilePath = os.path.join(self.acccountDir, f'{self.currentAccount}.json')

        with open(accountFilePath, 'r') as f:
            self.accountSettings = json.load(f)
            print(self.accountSettings)
