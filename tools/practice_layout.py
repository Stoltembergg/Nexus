"""Recognize the two verified 1080p Practice Tool panel sizes before clicking."""
import io, json, subprocess
from PIL import Image


def practice_layout():
    window = json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j']))
    if window.get('class') != 'LeagueofLegends' or window.get('at') != [0, 0] or window.get('size') != [1920, 1080]:
        raise SystemExit('practice controls require a focused 1920x1080 game at 0,0')
    px = Image.open(io.BytesIO(subprocess.check_output(['grim', '-g', '0,0 1920x1080', '-']))).convert('RGB').load()
    def score(rect):
        x0,y0,x1,y1=rect
        points = [(x,y0) for x in range(x0,x1)] + [(x,y1) for x in range(x0,x1)] + [(x0,y) for y in range(y0,y1)] + [(x1,y) for y in range(y0,y1)]
        return sum(px[x,y][0]>90 and px[x,y][1]>70 and px[x,y][0]>px[x,y][2]*1.3 for x,y in points)/len(points)
    small, large = score((15,216,46,247)), score((21,95,63,137))
    if max(small,large) < .4:
        raise SystemExit('practice panel geometry not recognized: refusing coordinate clicks')
    if large > small:
        return dict(x=42,up=50,down=1000,level=311,refresh=(117,165,214),revive=457,teleport=408,towers=583,minions=679,baron=214,skills=(758,825,890,956),skill_y=922)
    return dict(x=30,up=183,down=877,level=372,refresh=(232,266,301),revive=480,teleport=443,towers=570,minions=641,baron=302,skills=(827,870,914,957),skill_y=974)
