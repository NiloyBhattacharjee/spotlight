# Runs slopcannon on its own every day through Windows Task Scheduler: the books page, the Reddit stories page and the SCP page,
# each twice a day, with its settings in books.env / stories.env / scp.env (see page.env.example). Run once (again after changing a time):  powershell -ExecutionPolicy Bypass -File schedule.ps1
# The PC has to be on and you signed in (a locked screen is fine). Missed runs start as soon as it's back on.
# Output goes to logs\<page>.log. Remove a page with:  Unregister-ScheduledTask "slopcannon books"

$dir = $PSScriptRoot
$py = (Get-Command python).Source
New-Item -ItemType Directory -Force "$dir\logs" | Out-Null

# A run that fails (no internet, a busy API) tries twice more, 20 minutes apart; one never overlaps the next.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 20)

function Add-Page($name, $reelArgs, $times) {
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -WorkingDirectory $dir `
        -Argument "/c `"`"$py`" -u slopcannon.py $reelArgs >> logs\$name.log 2>&1`""
    $triggers = $times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
    Register-ScheduledTask -TaskName "slopcannon $name" -Action $action -Trigger $triggers -Settings $settings -Force | Out-Null
    Write-Output "slopcannon ${name}: daily at $($times -join ', ')"
}

# Book reels take about 20 minutes to make, so they start 20 minutes before the time they should go out.
Add-Page "books" "--book --env books.env" @("10:40", "18:40")
# Reddit reels take a few minutes.
Add-Page "stories" "--reddit --env stories.env" @("12:55", "20:55")
# SCP reels take about 10 minutes (Chatterbox on CPU); they go out around 5 pm and 11 pm, when horror does best.
Add-Page "scp" "--scp --env scp.env" @("16:50", "22:50")
