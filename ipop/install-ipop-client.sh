#!/bin/sh

yum -y install ipop rocks-ipop

/sbin/chkconfig --add ipop

grep -v ip4 ipopserver.info > /opt/ipop/etc/ipopserver.info

cat /etc/grub.conf | sed 's/KEYTABLE=us/KEYTABLE=us ipv6.disable=0/' > grub.conf
chmod 644 grub.conf
cp grub.conf /etc/grub.conf
