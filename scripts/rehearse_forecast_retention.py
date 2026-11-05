#!/usr/bin/env python3
import argparse
import json
from cryptoforge.forecast_retention_rehearsal import rehearse_split


def main():
    parser = argparse.ArgumentParser(description='Isolated diagnostic snapshot split rehearsal')
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--preflight',required=True)
    parser.add_argument('--preflight-sha256',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    result = rehearse_split(args.manifest,args.manifest_sha256,args.preflight,args.preflight_sha256,args.output)
    print(json.dumps({'output':args.output,'counts':result['counts'],'files':result['files'],
                      'actual_recording_restored':False},ensure_ascii=False))


if __name__ == '__main__':main()
