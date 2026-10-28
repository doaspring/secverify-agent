#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check an *actual* SecVerify contest ZIP after GLM5.3 builds and user supplies real links.
Usage:
python validate_submission.py --zip "单位-SecVerifyAgent-张三-13800138000-20261104.zip" \
 --app-url "https://actual-public-app" --video-url "https://actual-cloud-video" \
 --video-file "video.mp4" --out "submission_audit.json"
--app-url/--video-url/--video-file are optional: omitting them downgrades the related
checks to WARN so the structure-only pass can run before links exist.
This validator is not itself proof of actual login-free access or LIVE model execution.
"""
from pathlib import Path
import argparse, hashlib, io, json, re, subprocess, datetime, sys, zipfile
try: import fitz
except ImportError: fitz=None

def check(report,ok,label,extra="",critical=True):
    severity = "PASS" if ok else ("FAIL" if critical else "WARN")
    report["checks"].append({"result":severity,"item":label,"detail":extra})
    return ok

def pkg_safe(names):
    return not any(n.startswith(("/", "\\")) or "\\" in n or re.match(r"^[A-Za-z]:", n)
                   or ".." in n.split("/") for n in names)

def video_probe(p):
    raw=subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,width,height",
         "-of","json",str(p)],timeout=20)
    d=json.loads(raw.decode())
    v=next((x for x in d.get("streams",[]) if x.get("codec_type")=="video"),{})
    return float(d.get("format",{}).get("duration",0)),int(v.get("width",0)),int(v.get("height",0))

def inspect_zip(args):
    r={"timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "file":str(args.zip),"checks":[]}
    zpath=Path(args.zip)
    if not check(r,zpath.exists(),"outer zip exists"):
        return r
    stem=zpath.stem
    parts=stem.split("-")
    if len(parts)<5:
        valid=False
        check(r,False,"outer filename has at least 5 dash-separated fields",stem)
    elif len(parts)>5:
        # A field itself contains '-'; the official format cannot be split unambiguously.
        valid=False
        check(r,False,"outer filename exact 5 fields",
              "a field contains an extra '-'; confirm naming with organizers (单位简称-作品名称-队长姓名-手机号-YYYYMMDD.zip)",
              critical=False)
    else:
        valid=(all(parts) and re.fullmatch(r"\d{7,15}",parts[3]) and re.fullmatch(r"\d{8}",parts[4]))
        check(r,valid,"outer filename exact 5 fields","单位简称-作品名称-队长姓名-手机号-YYYYMMDD.zip")
    if valid:
        try: datetime.datetime.strptime(parts[4],"%Y%m%d")
        except ValueError:check(r,False,"date in filename is valid")
        if any("待填" in s or "placeholder" in s.lower() for s in parts):
            check(r,False,"no placeholder in name")
    r["outer_sha256"]=hashlib.sha256(zpath.read_bytes()).hexdigest()
    try:
        with zipfile.ZipFile(zpath) as outer:
            check(r,outer.testzip() is None,"outer zip CRC")
            files=[x for x in outer.namelist() if not x.endswith("/")]
            check(r,pkg_safe(files),"outer paths safe")
            check(r,len(files)==2,"outer contains exactly two files",str(files))
            pfs=[x for x in files if x.lower().endswith(".pdf")]
            zfs=[x for x in files if x.lower().endswith(".zip")]
            if not check(r,len(pfs)==1 and len(zfs)==1,"outer includes one PDF + one code ZIP"):
                return r
            pdf=outer.read(pfs[0])
            check(r,pdf.startswith(b"%PDF"),"technical PDF signature")
            if fitz is None:
                check(r,False,"PDF text/link verification","install pymupdf",critical=True)
            else:
                with fitz.open(stream=pdf,filetype="pdf") as document:
                    txt="\n".join(p.get_text() for p in document)
                    uris=[li.get("uri") for p in document for li in p.get_links()]
                    check(r,len(txt.strip())>250,"technical PDF searchable text")
                    for name,u in [("app",args.app_url),("video",args.video_url)]:
                        if not u:
                            check(r,False,f"{name} URL not provided",
                                  "pass --app-url/--video-url to enable this check",critical=False)
                            continue
                        check(r,u.startswith("https://") and "localhost" not in u and "127.0.0.1" not in u,
                              f"{name} link is a public HTTPS URL")
                        check(r,u in txt or u in uris,f"{name} URL actually present in technical PDF")
                    forbidden=["【待填写","TODO_LINK","your-public-app","your-video-link"]
                    check(r,not any(x in txt for x in forbidden),"no known URL placeholders in PDF")
            data=outer.read(zfs[0])
            with zipfile.ZipFile(io.BytesIO(data)) as inner:
                check(r,inner.testzip() is None,"inner zip CRC")
                names=[x for x in inner.namelist() if not x.endswith("/")]
                check(r,pkg_safe(names),"inner paths safe")
                wanted=["README.md","app.py","MODEL_WEIGHTS_README.txt"]
                for w in wanted:
                    check(r,any(x==w or x.endswith("/"+w) for x in names),f"inner has {w}")
                for f in ["src/","tests/","demos/"]:
                    check(r,any(f in x for x in names),f"inner has {f}")
                junk=[x for x in names if any(seg in {"__pycache__",".git",".pytest_cache",
                     ".venv","node_modules"} for seg in x.split("/")) or x.startswith("artifacts/")]
                check(r,not junk,"inner zip free of build/VCS/artifact dirs",str(junk),critical=False)
                check(r,any(x.endswith("pyproject.toml") or x.endswith("requirements.lock") for x in names),
                      "inner has dependency specification")
                secretfiles=[x for x in names if x.split("/")[-1] in {".env","secrets.toml","id_rsa"} 
                             or x.endswith((".pem",".key"))]
                check(r,not secretfiles,"inner has no obvious secret files",str(secretfiles))
                # Lightweight scanner, not full security validation.
                # Intern keys may not use the sk- prefix, so match any long
                # value assigned to the known env names, plus generic token shapes.
                hit=[]
                patterns=[re.compile(r"INTERN_API_KEY\s*=\s*\S{16,}"),
                          re.compile(r"(?i)api[_-]?key\s*[:=]\s*[\"\']?[A-Za-z0-9._-]{16,}"),
                          re.compile(r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9._-]{16,}"),
                          re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")]
                for n in names:
                    if n.endswith((".py",".json",".md",".txt",".toml",".yaml")):
                        blob=inner.read(n)
                        if len(blob)<400_000:
                            text=blob.decode("utf-8",errors="ignore")
                            if any(p.search(text) for p in patterns):
                                hit.append(n)
                check(r,not hit,"basic credential regex scan",str(hit))
    except (OSError,zipfile.BadZipFile,KeyError) as e:
        check(r,False,"ZIP parsing",repr(e))
        return r
    if args.video_file:
        f=Path(args.video_file)
        if f.exists():
            try:
                dur,w,h=video_probe(f)
                r["video"]={"seconds":dur,"width":w,"height":h}
                check(r,dur<300 and w>=1280 and h>=720,"video <300s and >=720P",str(r["video"]))
            except Exception as e:
                check(r,False,"video ffprobe",repr(e))
        else: check(r,False,"local video provided but missing")
    else: check(r,False,"video resolution/duration not independently checked",
                "Provide --video-file and manually check cloud share permissions",critical=False)
    check(r,False,"manual gates outstanding",
         "Verify anonymous app and video URLs, LIVE Intern-S2 invocation, model-weight requirement, and actual contest upload receipt",
         critical=False)
    return r

def main():
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # avoid GBK UnicodeEncodeError on Windows consoles
    ap=argparse.ArgumentParser()
    ap.add_argument("--zip",type=Path,required=True)
    ap.add_argument("--app-url",default=None,help="public app URL; omit to skip link checks")
    ap.add_argument("--video-url",default=None,help="cloud video URL; omit to skip link checks")
    ap.add_argument("--video-file",default=None)
    ap.add_argument("--out",default="submission_audit.json")
    a=ap.parse_args()
    rpt=inspect_zip(a)
    rpt["status"]="FAIL" if any(x["result"]=="FAIL" for x in rpt["checks"]) else "PASS_WITH_MANUAL_GATES"
    Path(a.out).write_text(json.dumps(rpt,ensure_ascii=False,indent=2),encoding="utf-8")
    print(rpt["status"],sum(x["result"]=="PASS" for x in rpt["checks"]),"PASS",
          sum(x["result"]=="FAIL" for x in rpt["checks"]),"FAIL",a.out)
    for x in rpt["checks"]:print(f"  [{x['result']}] {x['item']}: {x['detail']}")
    return int(rpt["status"]=="FAIL")
if __name__=="__main__":
    raise SystemExit(main())
