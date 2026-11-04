# 🧭 Guide: How to Safely Check Your Drive Health Before Recovery

If you are reading this, your Windows 10 computer has likely crashed, and you might be feeling incredibly stressed, anxious, or worried about your personal files. **Take a deep breath. You are in the right place, and we are going to help you step-by-step.**

This guide will help you perform three quick, entirely safe health checks on your computer's hard drive *before* you use our recovery app. 

### Why are we doing this?
Our recovery tool is strictly **read-only**—it is designed to protect your data and will never change or delete anything on your drive. However, if your hard drive is physically broken or dying, even trying to read files can cause permanent data loss. 

Think of this guide like checking the structural safety of a building before entering it to save your belongings. If your drive passes these checks, it is safe to use our software. If it fails, it means your drive needs professional hardware care.

---

## 🛠️ Step 1: Access the Windows Command Prompt (Two Methods)

To check your drive, we need to open a tool called the **Command Prompt**. Because a crashing computer often has missing or broken recovery tools, we have two ways to get there. 

### Method A: Use your computer's built-in tools
1. **Turn on your computer.**
2. As soon as it starts trying to load Windows (you might see a spinning circle of dots), **press and hold the physical Power Button** on your computer until it shuts down completely.
3. Turn your computer on again. Repeat this process **2 or 3 times**.
4. If successful, Windows will boot into a blue screen that says **Choose an option** or **Automatic Repair**.
5. Click on **Troubleshoot** > **Advanced options** > **Command Prompt**.

### Method B: If Method A fails (You need a Windows Installation USB)
If your computer just keeps crashing, loops forever, or stays completely black, your system's built-in recovery tools are missing. 
1. You will need to plug in a **bootable Windows 10 Installation USB** (you can create one for free on any working computer using Microsoft's Media Creation Tool).
2. Turn on your PC and tell it to boot from the USB drive (usually by tapping **F12**, **F11**, or **F2** as soon as it starts).
3. On the first screen that asks for your language and keyboard layout, click **Next**.
4. On the next screen, _**do not click "Install now"**_. Instead, look at the bottom-left corner and click **Repair your computer**.
5. Click on **Troubleshoot** > **Advanced options** > **Command Prompt**.

*Once you see a black window with white text, you are ready for Step 2.*

---

## 🛑 Step 2: The "Self-Diagnosis" Check (S.M.A.R.T.)

Before we look at any files, we must immediately check if the drive's physical hardware is actively dying. Modern hard drives have an internal monitor that tracks their own hardware health.

1. Type the following text exactly as it looks below into the black window:
   ```cmd
   wmic diskdrive get status
   ```
2. Press the **Enter** key on your keyboard.

### What the results mean:
* **If it says `OK`:** Your drive's physical hardware reports that it is stable! It is safe to proceed to Step 3.
* **If it says `Pred Fail` or `Caution`:** **Stop immediately.** Your drive has failed its hardware self-test. Do not open Notepad, do not try to browse files, and do not run recovery apps. Turn off the computer. Your best option is to send the drive to a professional data recovery service to save your files.

---

## 🔍 Step 3: Find Your True Windows Drive Letter (The Notepad Trick)

When your computer crashes into recovery mode, Windows often shuffles your drive letters. Your primary drive might shift from `C:` to `D:`, `E:`, or another letter entirely. Instead of guessing using command-line codes, we will use a secret visual file browser.

1. In the black window, type this single word exactly as it looks:
   ```cmd
   notepad
   ```
2. Press the **Enter** key on your keyboard. A blank Notepad window will pop up.
3. In the top-left corner of Notepad, click **File**, then click **Open...**.
4. A window will appear that looks like a normal file explorer. On the left-hand side, click on **This PC**.
5. Look at the drives listed under "Devices and drives". Double-click through them until you find the one that contains folders named **Users**, **Program Files**, and **Windows**. 
6. **Look closely at the letter next to that drive (for example: `Local Disk (D:)` or `Local Disk (E:)`).** 
7. **Write that letter down!** This is your true Windows drive letter for the final checks.
8. *Safety Note:* Do not double-click or try to open large personal files inside this Notepad window. Notepad will freeze trying to read them. 
9. Close the Notepad window. You will be back in the black Command Prompt window.

---

## 🟢 Step 4: The Physical Sector Check (`chkdsk`)

Next, we need to check if the drive has any "bad spots" (sectors) that make files physically unreadable. 

Type the following command (**Replace the `C:` in the command below with the exact letter you wrote down in Step 3**):
```cmd
chkdsk C: /f /r
```
Press **Enter**. 

*Note: This scan checks every physical corner of your drive and can take anywhere from 30 minutes to several hours depending on how large your drive is. It is completely normal for it to look "stuck" on a percentage for a long time. Let it finish.*

### What the results mean:
* **If it finishes successfully with 0 bad sectors:** Your drive surface is healthy! Move on to the final check.
* **If it freezes completely for many hours, makes clicking or grinding noises, or reports a high number of "bad sectors":** The drive is physically unstable. Stop here and avoid running further software scans.

---

## 🟢 Step 5: The Registry Safety Check

Our recovery application reads your Windows "Registry" (the database where Windows stores your settings and application layout) to figure out where your files are hidden. We want to make sure this database is readable before our tool opens it.

Type the following command exactly as written (**Replace `C:` with the exact letter you wrote down in Step 3**):
```cmd
reg load HKLM\OfflineSoftware C:\Windows\System32\config\SOFTWARE
```
Press **Enter**.

### What the results mean:
* **If it says `The operation completed successfully.`:** Your registry is readable! Type `reg unload HKLM\OfflineSoftware` and press **Enter** to safely clean up. You are completely clear to close this window and proceed to use our **Windows 10 Disaster Recovery App**!
* **If it gives an error saying the file is corrupted or unreadable:** The Windows database is broken. **Do not panic.** Our app can still look for your files using its alternative "Manifest" file-system scanning feature (which bypasses the registry entirely), but it means your old app layouts won't be reconstructed automatically. 

---

## 👋 Next Steps
If your drive safely passed the checks, you have successfully ruled out a catastrophic hardware failure! You can turn off your PC, insert your Ubuntu 24.04 Live USB, and follow the main instructions in our README to begin locating and protecting your irreplaceable files.
