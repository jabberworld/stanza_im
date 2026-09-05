#! /bin/bash
# converts svg icons to png format
# requires librsvg-bin 

# target directory to where save PNGs
target="."

# create target directory
#mkdir $target

# setting background-color
colour=ffffff
# setting transparency of background colour (0 transparent, 255 solid)
alpha=0

for soubor in *.svg
do
   rsvg $soubor $target/${soubor%%.*}.png		# ${soubor%%.*} removes extension from the filename
   echo "$soubor - konverze hotova"
   
done
