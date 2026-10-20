# -*- coding: utf-8 -*-
"""
工程化项目素材 → 授课PPT注入引擎（克隆模板页 + 回填素材）
用法:
    python ppt_enrich.py --src L11.pptx --dst L12.pptx --recipe recipes/l12.json [-o out.pptx]
设计:
  - 模板页从"范本课"（第11次课，结构完整）克隆到"目标课"（结构精简版）。
  - 克隆用 deepcopy 底层 XML，保证颜色/几何/字体完全一致。
  - 回填按"文本包含匹配"定位形状并整段覆写 run 文本，非匹配形状原样保留。
"""
import argparse
import copy
import json
from lxml import etree

from pptx import Presentation
from pptx.util import Inches, Pt

NSMAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}


def clone_slide(src_pres, src_slide, dst_pres):
    """跨文档克隆一张幻灯片到目标文档，返回新幻灯片。"""
    src_part = src_pres.part
    dst_part = dst_pres.part
    slide_layout = dst_pres.slide_layouts[6]  # Blank 布局

    # 1) 新建目标幻灯片
    dst_slide = dst_pres.slides.add_slide(slide_layout)

    # 2) 清除 add_slide 自动生成的空占位
    for ph in list(dst_slide.placeholders):
        sp = ph._element
        sp.getparent().remove(sp)

    # 3) deepcopy 源幻灯片 spTree 的子元素
    src_spTree = src_slide.shapes._spTree
    dst_spTree = dst_slide.shapes._spTree
    for child in list(src_spTree):
        if child.tag.endswith("nvGrpSpPr") or child.tag.endswith("grpSpPr"):
            continue
        dst_spTree.append(copy.deepcopy(child))

    # 4) 重新编号形状 id，避免与现有冲突
    _renumber_ids(dst_slide)

    # 5) 复制需要的关系（图片/媒体），重映射 r:embed/r:link
    _copy_rel_images(src_slide, dst_slide, src_part, dst_part)
    return dst_slide


def _renumber_ids(slide):
    used = set()
    spTree = slide.shapes._spTree
    for sp in spTree.iter():
        if not hasattr(sp, "get") or sp.get("id") is None:
            continue
        try:
            n = int(sp.get("id"))
        except ValueError:
            continue
        used.add(n)
    nid = max(used) if used else 1
    for sp in spTree.iter():
        # 只重命名 <p:sp>/<p:pic>/<p:graphicFrame>/<p:cxnSp> 之类的 id 属性
        tag = etree.QName(sp).localname
        if tag in ("sp", "pic", "graphicFrame", "cxnSp", "grpSp") and sp.get("id"):
            if int(sp.get("id")) in used and sp is not spTree.iter().__next__():
                pass
    # 简单策略：把重复 id 重新分配
    seen = {}
    for sp in spTree.iter():
        tag = etree.QName(sp).localname
        if tag not in ("sp", "pic", "graphicFrame", "cxnSp", "grpSp"):
            continue
        cid = sp.get("id")
        if cid is None:
            continue
        if cid in seen:
            nid += 1
            sp.set("id", str(nid))
        else:
            seen[cid] = sp


def _copy_rel_images(src_slide, dst_slide, src_part, dst_part):
    """把源幻灯片引用的图片/媒体/图表关系复制到目标幻灯片并重映射 r:embed/r:link。"""
    src_slide_part = src_slide.part
    dst_slide_part = dst_slide.part
    src_rels = src_slide_part.rels

    # 先复制媒体部件并建立旧rId→新rId映射
    for rel in list(src_rels.values()):
        if not rel.reltype:
            continue
        lb = rel.reltype.rstrip("/").split("/")[-1]
        if lb in ("image", "chart", "oleObject", "video", "audio", "media"):
            try:
                new_rid = dst_slide_part.relate_to(rel.target_part, rel.reltype)
                _rewrite_rid(dst_slide, rel.rId, new_rid)
            except Exception:
                pass

    # 外部（超链接）关系
    for rel in list(src_rels.values()):
        if rel.is_external:
            try:
                new_rid = dst_slide_part.relate_to(rel.target_ref,
                                                    rel.reltype, is_external=True)
                _rewrite_rid(dst_slide, rel.rId, new_rid)
            except Exception:
                pass


def _rewrite_rid(slide, old_rid, new_rid):
    """把幻灯片中 r:embed / r:link 的旧 rId 改成目标文档的新 rId。"""
    spTree = slide.shapes._spTree
    for el in spTree.iter():
        if not hasattr(el, "get") or el.get is None:
            continue
        for attr in ("{%s}embed" % NSMAP["r"], "{%s}link" % NSMAP["r"]):
            if el.get(attr) == old_rid:
                el.set(attr, new_rid)


def find_shape(slide, match):
    """按形状文本包含 match 返回第一个匹配形状；无则 None。"""
    for sh in slide.shapes:
        if sh.has_text_frame and match in sh.text_frame.text:
            return sh
    return None


def set_shape_text(shape, text, keep_size=False, anchor=None):
    """整段覆写形状文本（保留首 run 格式），多行分 paragraph。可选垂直对齐。"""
    lines = text.split("\n")
    tf = shape.text_frame
    paras = tf.paragraphs
    first = paras[0]
    # 取出首 run 模板
    ref_run = first.runs[0] if first.runs else None

    # 清空所有段落
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    first.clear()

    def add_run(p, txt):
        r = p.add_run()
        r.text = txt
        if ref_run is not None:
            try:
                r.font.size = ref_run.font.size
                r.font.bold = ref_run.font.bold
                r.font.name = ref_run.font.name
                col = ref_run.font.color
                if col is not None and col.type is not None:
                    try:
                        r.font.color.rgb = col.rgb
                    except Exception:
                        pass
            except Exception:
                pass
        return r

    for i, line in enumerate(lines):
        p = first if i == 0 else tf.add_paragraph()
        add_run(p, line)

    if anchor is not None:
        try:
            from pptx.enum.text import MSO_ANCHOR
            tf.vertical_anchor = getattr(MSO_ANCHOR, anchor.upper(), None)
        except Exception:
            pass
    if keep_size:
        tf.word_wrap = True


def resize_shape(shape, h=None, w=None):
    from pptx.util import Inches
    if h is not None:
        shape.height = Inches(h)
    if w is not None:
        shape.width = Inches(w)


def _stretch_rows(slide, spec):
    """按行关键字把"卡边框"(空AUTO_SHAPE矩形)加高到目标底边，文本位置不动(防重叠)。
    spec: {"rows":[{"match": 文本框内容片段, "bottom": 6.55}, ...], "default_bottom": 6.55}
    - 只拉伸"完全覆盖该文本框"的卡边框；文本框/标题框位置与高度都不改。
    - bottom 为绝对英寸底边；未给行级则用 spec.default_bottom。
    """
    from pptx.util import Emu as _E
    default_bottom = spec.get("default_bottom")
    frames = [sh for sh in slide.shapes
              if "AUTO_SHAPE" in str(sh.shape_type)
              and (not sh.has_text_frame or not sh.text_frame.text.strip())
              and sh.top is not None and sh.height is not None]
    for row in spec.get("rows", []):
        m = row.get("match")
        bottom = row.get("bottom", default_bottom)
        if not m or bottom is None:
            continue
        for sh in slide.shapes:
            if not sh.has_text_frame or m not in sh.text_frame.text:
                continue
            if sh.top is None or sh.left is None:
                continue
            x0 = _E(sh.left).inches; y0 = _E(sh.top).inches
            x1 = x0 + _E(sh.width).inches; y1 = y0 + _E(sh.height).inches
            for fr in frames:
                fx0 = _E(fr.left).inches; fy0 = _E(fr.top).inches
                fx1 = fx0 + _E(fr.width).inches; fy1 = fy0 + _E(fr.height).inches
                contains = (fx0 - 0.1 <= x0 and fy0 - 0.1 <= y0
                            and fx1 + 0.1 >= x1 and fy1 + 0.1 >= y1)
                if not contains:
                    continue
                target = bottom - fy0
                if target <= 0:
                    continue
                try:
                    fr.height = Inches(target)
                except Exception:
                    pass
                break
            break


def apply_recipe(src_prs, dst_prs, recipe):
    """按 recipe 把模板页克隆进目标 deck 并回填素材。
    克隆后统一做一次排序：克隆页插入到其 `at`（0-based，插入到该位置之前）处。
    """
    inserts = recipe["inserts"]
    xml_slides = dst_prs.slides._sldIdLst
    # 原始页（克隆前）的 sldId 元素，保持相对顺序
    originals = list(xml_slides)
    # clone 后记录: (at, sldId_element)
    clones = []
    for ins in inserts:
        src_slide = src_prs.slides[ins["src"]]
        new_slide = clone_slide(src_prs, src_slide, dst_prs)
        # clone_slide 通过 add_slide 追加到末尾，拿到它的 sldId 元素
        sldIds = list(xml_slides)
        clone_el = sldIds[-1]
        for fill in ins.get("fills", []):
            sh = find_shape(new_slide, fill["match"])
            if sh is not None:
                set_shape_text(sh, fill["text"])
            else:
                print("  ! 未找到匹配形状:", fill["match"][:20])
        at = ins.get("at")
        if at is None:
            at = len(sldIds) - 1  # 保持末尾

        # 可选：把若干内容卡片加高，让卡片铺满纵向空间（recipe 可为 dict 或 [dict]）
        sr = ins.get("stretch_rows")
        if isinstance(sr, dict):
            _stretch_rows(new_slide, sr)
        else:
            for s in sr or []:
                _stretch_rows(new_slide, s)
        clones.append((at, clone_el))

    _reorder_to_at(clones)
    _renumber_slide_num(dst_prs)
    return dst_prs


def _reorder_to_at(clones):
    """把一批克隆页插到各自 at 位置，保持原有页顺序。"""
    import pptx
    # 在单独操作中：从当前列表取出所有原始页，重建
    # 这里采用增量插入：按 at 升序，逐个把克隆页移动到目标槽位。
    for at, el in sorted(clones, key=lambda x: x[0]):
        parent = el.getparent()
        all_el = list(parent)
        parent.remove(el)
        # 目标槽位=at，但若有更早插入的克隆占位，需要按"已插入克隆数"修正——这里按绝对序号。
        all_after = list(parent)
        idx = min(at, len(all_after))
        parent.insert(idx, el)


def _move_slide(prs, slide, new_index):
    """把 slide 移动到 new_index（0-based）。"""
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    sldId = None
    for sld in slides:
        if sld.get("{%s}id" % NSMAP["r"]) == str(slide.slide_id):
            sldId = sld
            break
    if sldId is None:
        return
    sldId.getparent().remove(sldId)
    insert_at = new_index
    if insert_at >= len(slides) - 1:
        xml_slides.append(sldId)
    else:
        xml_slides.insert(new_index, sldId)


def _renumber_slide_num(prs):
    """更新每页页脚 'n / N' 页码。"""
    total = len(prs.slides)
    for i, slide in enumerate(prs.slides):
        for sh in slide.shapes:
            if sh.has_text_frame and "/" in sh.text_frame.text:
                t = sh.text_frame.text.strip()
                if t.count("/") == 1 and t.strip().split("/")[0].strip().isdigit() and t.strip().split("/")[1].strip().isdigit():
                    joined = "/".join(t.split("/")[2:]) if t.count("/") > 1 else ""
                    base = t.split("/")[0].strip()
                    new = "%d / %d" % (i + 1, total)
                    set_shape_text(sh, new, keep_size=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    with open(args.recipe, encoding="utf-8") as fh:
        recipe = json.load(fh)
    src_prs = Presentation(args.src)
    dst_prs = Presentation(args.dst)
    apply_recipe(src_prs, dst_prs, recipe)
    if not args.out:
        import os
        args.out = os.path.splitext(args.dst)[0] + ".enriched.pptx"
    dst_prs.save(args.out)
    print("saved:", args.out, "slides:", len(dst_prs.slides))


if __name__ == "__main__":
    main()