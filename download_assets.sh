#!/bin/bash

mkdir -p map_data

curl -L "https://drive.google.com/file/d/1cjsj3_OA_sFJSX9_-vYpEahndwv7whyx/view?usp=sharing" -o map_data.zip

unzip map_data.zip

rm map_data.zip