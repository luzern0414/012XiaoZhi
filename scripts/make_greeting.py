"""Build a local 360 px EchoEar greeting screen using Windows CJK fonts."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
image=Image.new('RGB',(360,360),'#f5f7f0')
draw=ImageDraw.Draw(image)
font_path='C:/Windows/Fonts/msyh.ttc'
def text(y,value,size,color):
    font=ImageFont.truetype(font_path,size)
    draw.text((180,y),value,font=font,fill=color,anchor='mt')
draw.rounded_rectangle((152,57,208,113),radius=19,fill='#28664b')
font=ImageFont.truetype(font_path,30)
draw.text((180,67),'知',font=font,fill='white',anchor='mt')
text(139,'你好，我是小智',27,'#26352f')
text(184,'很高兴见到你',19,'#80917f')
draw.line((135,235,225,235),fill='#d5dfd1',width=1)
text(258,'有什么想问我的？',18,'#425a46')
text(292,'说“你好小智”开始对话',12,'#899781')
target=ROOT/'data/hardware/greeting.jpg'
image.save(target,quality=93,subsampling=0)
print(target)
