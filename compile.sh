#!/bin/bash
g++ -shared -fPIC -o studentlib.so studentlib.cpp -lsqlite3 -O3