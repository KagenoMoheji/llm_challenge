Add-Type -AssemblyName System.Drawing
function Create-Icon($size, $path) {
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)
    
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 37, 99, 235))
    $g.FillEllipse($brush, 1, 1, ($size - 2), ($size - 2))
    
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White, [Math]::Max(2, [int]($size / 10)))
    $center = [int]($size / 2)
    $g.DrawLine($pen, $center, $center, $center, [int]($size * 0.25))
    $g.DrawLine($pen, $center, $center, [int]($size * 0.75), $center)
    
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bmp.Dispose()
}

$dir = "C:\Users\reegg\.gemini\antigravity\scratch\scheduled-clicker-extension\icons"
Create-Icon 16 "$dir\icon16.png"
Create-Icon 48 "$dir\icon48.png"
Create-Icon 128 "$dir\icon128.png"
Write-Host "Icons generated successfully."
