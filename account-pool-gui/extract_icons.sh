#!/bin/bash
# 从 AI 生成的多图标精灵图中提取单个图标并设置透明背景
# 用法: ./extract_icons.sh "Generated Image.png" 行数 列数

SOURCE="$1"
ROWS=${2:-2}      # 默认2行
COLS=${3:-2}      # 默认2列
OUTPUT_PREFIX="icon"

# 获取图片尺寸
WIDTH=$(identify -format "%w" "$SOURCE")
HEIGHT=$(identify -format "%h" "$SOURCE")

# 计算单个图标尺寸
ICON_W=$((WIDTH / COLS))
ICON_H=$((HEIGHT / ROWS))

echo "图片尺寸: ${WIDTH}x${HEIGHT}, 图标网格: ${ROWS}x${COLS}, 单图标: ${ICON_W}x${ICON_H}"

# 循环裁剪每个图标
for ((row=0; row<ROWS; row++)); do
    for ((col=0; col<COLS; col++)); do
        INDEX=$((row * COLS + col + 1))
        X=$((col * ICON_W))
        Y=$((row * ICON_H))
        OUTPUT="${OUTPUT_PREFIX}_${INDEX}.png"
        
        echo "提取图标 $INDEX (位置: ${X},${Y}, 尺寸: ${ICON_W}x${ICON_H})"
        
        # 裁剪 + 背景变透明 + 调整大小
        convert "$SOURCE" \
            -crop ${ICON_W}x${ICON_H}+${X}+${Y} \
            +repage \
            -fill none -fuzz 15% -draw "matte 0,0 floodfill" \
            -trim +repage \
            -resize 512x512 \
            -background none -gravity center -extent 512x512 \
            "$OUTPUT"
    done
done

echo "完成！已生成:"
ls -la ${OUTPUT_PREFIX}_*.png
