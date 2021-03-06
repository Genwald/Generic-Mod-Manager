import os
import shutil
import configparser
import sys
import nx
import _nx
import re
from nx.utils import AnsiMenu
configFile = "ModManager.ini"
AnsiMenu.firstrun = True
printb = sys.stdout.buffer.write
activeGame = ""


class ExitToHBMenu(Exception):
    pass


# modified AnsiMenu.poll_input to resume marker position and have quicker movement options
def poll_input(self):
    if self.firstrun:
        # todo: do this differently to prevent delay when placing marker near the bottom of the screen
        self.console.write(b" "+bytes("\n"*self.selected_idx+"\r>\r", 'UTF-8'))
        self.firstrun = False
    _nx.hid_scan_input()
    keys_down = _nx.hid_keys_down(self.CONTROLLER_P1_AUTO)

    if keys_down & self.KEY_A:
        return True
    elif keys_down & (1 << 10):
        raise ExitToHBMenu
    elif keys_down & self.KEY_UP:
        if self.selected_idx > 0:
            self.selected_idx -= 1
            self.console.write(b" \x1b[1A\r>\r")
            self.console.flush()
    elif keys_down & self.KEY_DOWN:
        if self.selected_idx < len(self.entries) - 1:
            self.selected_idx += 1
            self.console.write(b" \n\r>\r")
            self.console.flush()
    elif keys_down & (1 << 14):
        if self.selected_idx < len(self.entries) - 5:
            self.selected_idx += 5
            self.console.write(b" \n\n\n\n\n\r>\r")
            self.console.flush()
        else:
            self.console.write(bytes((" " + "\n"*((len(self.entries) - 1) - self.selected_idx))+"\r>\r", "UTF-8"))
            self.selected_idx = len(self.entries) - 1
            self.console.flush()
    elif keys_down & (1 << 12):
        if self.selected_idx > 5:
            self.selected_idx -= 5
            self.console.write(b" \x1b[1A\x1b[1A\x1b[1A\x1b[1A\x1b[1A\r>\r")
            self.console.flush()
        else:
            self.console.write(bytes((" " + "\x1b[1A" * self.selected_idx) + "\r>\r", "UTF-8"))
            self.selected_idx = 0
            self.console.flush()

    return False


AnsiMenu.poll_input = poll_input


def removevalue(value):  # see if any option owns a value and then remove it
    for section in config.sections():
        for option in config.options(section):
            if config.get(section, option) == value:
                config.remove_option(section, option)
        if not config.options(section):
            config.remove_section(section)


# todo: maybe move files instead of copying to speed things up. Or maybe add an option to choose.
def copymod(src, dst, filelist=None, primary=True):  # making this recursive is causing a lot of trouble
    global promptSkip
    global selected_mod
    global filecount
    # promptSkip: 0=none, 1=skip and answer yes, 2=skip and answer no
    if filelist is None:  # dang mutable defaults
        filelist = []
    # collect all files first so we can show progress
    # todo: maybe display something while searching for files
    # noticeable blank screen with >~50 files
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copymod(s, d, filelist, False)
        else:
            if not os.path.exists(d):  # or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                filelist.append([s, d])
            else:
                if promptSkip == 0:
                    fileowner = None
                    for section in config.sections():
                        for option in config.options(section):
                            if config.get(section, option) == d:
                                fileowner = section
                    if fileowner:
                        print("The mod \"" + fileowner.split("|")[1] + "\" from \"" + fileowner.split("|")[0] +
                              "\" is already using \"" + d + "\"\nReplace the file?\n")
                    else:
                        print(d + " already exists.\nReplace it?\n")
                    sys.stdout.flush()
                    saveidx = AnsiMenu.selected_idx
                    AnsiMenu.selected_idx = 0
                    answer_index = AnsiMenu(["Yes", "No", "Yes to all", "No to all"]).query()
                    AnsiMenu.selected_idx = saveidx
                    nx.utils.clear_terminal()
                    sys.stdout.flush()
                    if answer_index == 0:  # yes
                        os.remove(d)
                        filelist.append([s, d])
                        removevalue(d)
                    elif answer_index == 1:
                        filecount += 1
                    elif answer_index == 2:  # yes to all
                        promptSkip = 1
                    elif answer_index == 3:  # no to all
                        promptSkip = 2
                if promptSkip == 1:
                    os.remove(d)  # not 100% sure I want this, copyfileobj should overwrite
                    #  but I was having problems without this
                    filelist.append([s, d])
                    removevalue(d)
                if promptSkip == 2:
                    filecount += 1
    # do actual copying
    if primary:  # only reached once all recursive calls are done
        filecount += len(filelist)
        for i, file in enumerate(filelist):
            nx.utils.clear_terminal()
            printb(b'Copying file ' + bytes(str(i+1), "UTF-8") + b' of ' + bytes(str(len(filelist)), "UTF-8") +
                   b"\nDo not exit while copying\x1b[1A\r")
            sys.stdout.buffer.flush()
            # I'm quite confused about where and why I need to flush.
            # If I don't here, nothing shows, but in other places it isn't needed.
            if not os.path.exists(os.path.dirname(file[1])):
                os.makedirs(os.path.dirname(file[1]))
            try:
                shutil.copyfileobj(open(file[0], 'rb'), open(file[1], 'wb'), 16*1024*1024)
            except OSError as err:
                raise OSError("\n\n\nHey, it looks like \"" + file[0] + "\" might be corrupt.") from err
            savemodinfo(selected_mod, file[1], filecount)
            # todo: investigate long (~1 second) blank screen after large transfer (linkle mod)


def delmod(mod):
    # printb(b"Removing files\n Do not exit")  # I don't think this is needed, deletes too fast to be visible
    sectionName = activeGame + "|" + mod
    for option in config.options(sectionName):
        file = config.get(sectionName, option)
        if os.path.exists(file):
            os.remove(file)
            try:
                os.removedirs(os.path.dirname(file))  # remove empty folders
            except OSError:  # throws OSError if there are still files in the folder
                pass  # do nothing if there are other files
    config.remove_section(sectionName)
    config.write(open(configFile, 'w'))


def savemodinfo(mod, file, length):
    # global activeGame
    sectionName = activeGame + "|" + mod
    if not config.has_section(sectionName):
        config.add_section(sectionName)
    option = len(config.options(sectionName))  # to make options not identical
    config.set(sectionName, str(length) + "," + str(option), file)
    config.write(open(configFile, 'w'))


# This feels like a mess. Maybe I ought to do a re-write of some of this
def makemenu(menulist, mainmenu=False):  # todo: rename variables to make more sense
    global pageNum
    global modFolder
    global originalModFolder
    global selected_mod
    global activeGame
    listLen = 38
    # separates the mod list into pages
    modsPages = [menulist[x:x + listLen] for x in range(0, len(menulist), listLen)]
    # this is the actual list of mods
    mods = modsPages[pageNum]
    # this will be the list we show with the current state of the mod
    modsPrint = list(modsPages[pageNum])
    width = 77  # Ansimenu uses the other 3
    for i, mod in enumerate(mods):  # todo: make it easier to tell which mod corresponds to which state
        if len(modsPrint[i]) > 68:
            modsPrint[i] = modsPrint[i][:65] + "..."
        if not mainmenu:
            section = activeGame + "|" + mod
            if config.has_section(section):
                totalfiles = int(config.options(section)[0].split(",")[0])
                active = len(config.options(section))
                fractionenabled = str(active) + "/" + str(totalfiles)
                if totalfiles > active:
                    modsPrint[i] += (width - (len(modsPrint[i]) + len(fractionenabled))) * " " + fractionenabled
                else:
                    modsPrint[i] += (width - (len(modsPrint[i]) + 6)) * " " + "ACTIVE"
            else:
                modsPrint[i] += (width - (len(modsPrint[i]) + 8)) * " " + "INACTIVE"
                # terminal is 80 characters wide in total
    # determine if next or previous page is selected
    if AnsiMenu.selected_idx > len(modsPrint):
        AnsiMenu.selected_idx = len(modsPrint) - 1
    if len(modsPages) > 1:
        if (pageNum + 1) < len(modsPages):
            modsPrint.append("[Next Page]")
        if pageNum != 0:
            modsPrint.append("[Previous Page]")

    if (pageNum == 0) & (not mainmenu):
        modsPrint.insert(0, "[Main Menu]")
        listLen += 1
    selected_index = AnsiMenu(modsPrint).query()

    # previous page on last page
    if (pageNum + 1 == len(modsPages)) & (selected_index + 1 == len(modsPrint)) & (len(modsPages) > 1):
        pageNum -= 1
        AnsiMenu.selected_idx = listLen  # todo: this works inconsistently in some cases due to prepending
    # previous page
    elif selected_index == listLen + 1:
        pageNum -= 1
        AnsiMenu.selected_idx = listLen
    # next page
    elif selected_index == listLen:
        pageNum += 1
        AnsiMenu.selected_idx = 0
    # Main Menu
    elif (pageNum == 0) & (selected_index == 0) & (not mainmenu):
        modFolder = originalModFolder
        AnsiMenu.selected_idx = 0
    elif not mainmenu:
        AnsiMenu.selected_idx = selected_index
        if pageNum == 0:
            selected_index -= 1
        selected_mod = mods[selected_index]
        nx.utils.clear_terminal()
        sys.stdout.flush()
        if config.has_section(activeGame + "|" + selected_mod):
            delmod(selected_mod)
        else:
            copymod(modFolder + "/" + selected_mod, layeredFSFolder)
    else:
        activeGame = mods[selected_index]
        modFolder = modFolder + "/" + activeGame


def natural_key(string_):  # for natural sorting
    return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_)]


if __name__ == '__main__':

    pageNum = 0
    config = configparser.RawConfigParser()
    config.read(configFile)
    # if config does't exit, add some default values
    if not config.has_section("|options|"):
        config.add_section("|options|")
    if not config.has_option("|options|", "modFolder"):
        config.set("|options|", "modFolder", "/mods")
    if not config.has_option("|options|", "layeredFSFolder"):
        config.set("|options|", "layeredFSFolder", "/atmosphere/titles")
    config.write(open(configFile, 'w'))

    modFolder = config.get("|options|", "modFolder")
    originalModFolder = config.get("|options|", "modFolder")  # for comparisons
    layeredFSFolder = config.get("|options|", "layeredFSFolder")

    try:
        while True:
            promptSkip = 0
            filecount = 0

            if not os.path.isdir(modFolder):
                nx.utils.clear_terminal()
                print("Your mods folder \"" + modFolder + "\" doesn't exit\n")
                sys.stdout.flush()
                AnsiMenu(["Create it?"]).query()
                os.mkdir(modFolder)
            if (modFolder == originalModFolder) & bool(os.listdir(modFolder)):
                gameList = os.listdir(modFolder)
                gameList = sorted(gameList, key=natural_key)
                nx.utils.clear_terminal()
                sys.stdout.flush()
                printb(b"Generic Mod Manager" + bytes(" " * 53, "UTF-8") + b"By Seth\n\n")  # Main menu
                makemenu(gameList, True)
                AnsiMenu.selected_idx = 0
            elif modFolder == originalModFolder:
                nx.utils.clear_terminal()
                print("Your mods folder \"" + modFolder + "\" looks empty\n"
                      "Add some mods to it or change the folder location in " + configFile +
                      "\n\nThe recommended folder format for mods is:\n"
                      "\"/ModsFolder/GameName/ModName/TitleID/ModFiles\"\n\n"
                      "For Example:\n\"/mods/Legend of Zelda/Bowser Hinox/01007EF00011E000/romfs/...\"\n")
                sys.stdout.flush()
                AnsiMenu(["try again?"]).query()
            elif os.listdir(modFolder):
                modFolderList = os.listdir(modFolder)  # seems to default to time added todo: consider adding new ways to sort
                # data = sorted(data,  key=str.lower)  # alphabetical

                nx.utils.clear_terminal()
                sys.stdout.flush()
                printb(b"Generic Mod Manager"+bytes(" "*53, "UTF-8")+b"By Seth\n\n")
                printb(bytes(" "*(40-(len(activeGame)//2))+activeGame+"\n"[:80], "UTF-8"))
                # printb(b"Warning: Exiting during an operation can cause mod files to be corrupted")
                makemenu(modFolderList)
            else:
                nx.utils.clear_terminal()
                print("This game folder, \""+modFolder+"\" doesn't seem to have any mods\n"
                      "Add some mods to it or change the folder location in "+configFile+"\n")
                sys.stdout.flush()
                selected_index = AnsiMenu(["[Main Menu]", "try again?"]).query()
                if selected_index == 0:
                    modFolder = originalModFolder
    except ExitToHBMenu:
        nx.utils.clear_terminal()
        sys.stderr.write("Press + again to exit")
        sys.stdout.flush()
