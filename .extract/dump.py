import os, io, json

base = r"D:/Peggy zhan/智能EC101/数据底座/第三阶段数据库设计/ec101-promotion-closure-validator/ec101-promotion-closure-validator"
out = io.open(base + "/../../.extract/refs_dump.txt", "w", encoding="utf-8")

def emit(path, label):
    out.write("\n\n========== " + label + " ==========\n")
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            out.write(f.read())
    except Exception as e:
        out.write("ERR " + str(e))

refs = os.path.join(base, "references")
for f in sorted(os.listdir(refs)):
    emit(os.path.join(refs, f), "references/" + f)

pr = os.path.join(base, "platform-rules")
for f in sorted(os.listdir(pr)):
    emit(os.path.join(pr, f), "platform-rules/" + f)

emit(os.path.join(base, "PROJECT.md"), "PROJECT.md")

# case configs
cases = os.path.join(base, "cases")
for d in sorted(os.listdir(cases)):
    dp = os.path.join(cases, d)
    if os.path.isdir(dp):
        for f in os.listdir(dp):
            if f.endswith(".json"):
                emit(os.path.join(dp, f), "case:" + d + "/" + f)

out.close()
print("DONE")
