#!/bin/sh -x

rocks add roll ipop*iso

rocks enable roll ipop

cd /export/rocks/install

rocks create distro

yum clean all

rocks run roll ipop > add-roll.sh

bash add-roll.sh  > add-roll.out 2>&1

cd /root

cat /etc/grub.conf | sed 's/KEYTABLE=us/KEYTABLE=us ipv6.disable=0/' > grub.conf
chmod 644 grub.conf
cp grub.conf /etc/grub.conf
