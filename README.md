# Fork Notes:
I'm calling my fork "ReMixamo-Downloader".

I found that verison had issues where it would hang around 200-300 downloads, so I fixed it. This verison requires PySide6 and Python 3.14+.

Forked from https://github.com/juanjo4martinez/mixamo-downloader.

I have updated the src directory for python users after successful testing to alleviate the hang issue.  I will plan to fix the .exe as well, but for now just use the Python instructions.


_Original ReadME below_:

# Mixamo Downloader

GUI to bulk download animations from [Mixamo](https://www.mixamo.com/).

This repository contains both the Python source code (in the `/src` folder) and an `.exe` file (in the `/dist` folder) to make things easier to Windows users.

### For Python users

Make sure you have [Python 3.10+](https://www.python.org/) installed on your computer, as well as the [PySide6](https://pypi.org/project/PySide6/) package:

```bash
pip install PySide6
```

Download the files from the `/src` folder to your own local directory, and double-click on the `main.pyw` script to launch the GUI.

### For non-technical users
If you don't have Python installed on your computer or you don't want to mess with all that coding stuff, download the `/dist` folder to your computer (~300MB) and run the `mixamo_downloader.exe`.

## How to use the Mixamo Downloader

1. Log into your Mixamo account.
2. Select/upload the character you want to animate.
3. Choose between downloading `All animations`, `Animations containing the word` and the `T-Pose (with skin)`.
4. You can optionally set an output folder where all animations will be saved.

   > If no output folder is set, FBX files will be downloaded to the folder where the program is running.
  
5. Press the `Start download` button and wait until it's done.
6. You can cancel the process at any time by pressing the `Stop` button.

> [!IMPORTANT]
> Downloading all animations can be quite slow. We're dealing with a total of 2346 animations, so don't expect it to be lighting fast.
