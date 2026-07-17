#target photoshop

/*
 * Compiled by photoshop_bridge.py. The bridge injects one validated job object
 * into the declaration below before sending this script to ExtendScript.
 */
(function () {
    var JOB = __JOB_JSON__;
    var originalDialogs = app.displayDialogs;
    var originalDocument = app.documents.length ? app.activeDocument : null;
    var initialDocuments = [];
    var initialDocumentRecords = [];
    var ownedDocuments = [];
    var builtLayers = [];
    var groups = {};
    var bootstrapLayer = null;

    function documentRecord(document) {
        var pathValue = null;
        try { pathValue = document.fullName.fsName; } catch (ignoredPath) {}
        return {name: document.name, path: pathValue, saved: Boolean(document.saved)};
    }
    function captureInitialDocuments() {
        var i;
        for (i = 0; i < app.documents.length; i += 1) {
            initialDocuments.push(app.documents[i]);
            initialDocumentRecords.push(documentRecord(app.documents[i]));
        }
    }
    function verifyInitialDocuments() {
        var missing = [];
        var i;
        var j;
        for (i = 0; i < initialDocuments.length; i += 1) {
            var found = false;
            for (j = 0; j < app.documents.length; j += 1) {
                if (initialDocuments[i] === app.documents[j]) {
                    found = true;
                    break;
                }
            }
            if (!found) { missing.push(initialDocumentRecords[i]); }
        }
        return {
            before: initialDocumentRecords,
            after: (function () {
                var records = [];
                for (var index = 0; index < app.documents.length; index += 1) {
                    records.push(documentRecord(app.documents[index]));
                }
                return records;
            }()),
            preserved: missing.length === 0,
            missing: missing
        };
    }

    function sid(value) { return stringIDToTypeID(value); }
    function cid(value) { return charIDToTypeID(value); }
    function px(value) { return UnitValue(Number(value), "px"); }
    function numberValue(value, fallback) {
        var parsed = Number(value);
        return isNaN(parsed) ? fallback : parsed;
    }
    function hexColor(value) {
        var raw = String(value || "#000000").replace("#", "");
        if (raw.length === 3) {
            raw = raw.charAt(0) + raw.charAt(0) + raw.charAt(1) + raw.charAt(1) + raw.charAt(2) + raw.charAt(2);
        }
        return {
            r: parseInt(raw.substring(0, 2), 16),
            g: parseInt(raw.substring(2, 4), 16),
            b: parseInt(raw.substring(4, 6), 16)
        };
    }
    function solidColor(value) {
        var rgb = hexColor(value);
        var color = new SolidColor();
        color.rgb.red = rgb.r;
        color.rgb.green = rgb.g;
        color.rgb.blue = rgb.b;
        return color;
    }
    function rgbDescriptor(value) {
        var rgb = hexColor(value);
        var descriptor = new ActionDescriptor();
        descriptor.putDouble(cid("Rd  "), rgb.r);
        descriptor.putDouble(cid("Grn "), rgb.g);
        descriptor.putDouble(cid("Bl  "), rgb.b);
        return descriptor;
    }
    function ensureFolder(pathValue) {
        var file = new File(pathValue);
        if (!file.parent.exists && !file.parent.create()) {
            throw new Error("Cannot create output folder: " + file.parent.fsName);
        }
        return file;
    }
    function jsonQuote(value) {
        return '"' + String(value)
            .replace(/\\/g, "\\\\")
            .replace(/"/g, '\\"')
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n")
            .replace(/\t/g, "\\t") + '"';
    }
    function toJson(value) {
        var i;
        var parts;
        if (value === null || value === undefined) { return "null"; }
        if (typeof value === "string") { return jsonQuote(value); }
        if (typeof value === "number") { return isFinite(value) ? String(value) : "null"; }
        if (typeof value === "boolean") { return value ? "true" : "false"; }
        if (value instanceof Array) {
            parts = [];
            for (i = 0; i < value.length; i += 1) { parts.push(toJson(value[i])); }
            return "[" + parts.join(",") + "]";
        }
        parts = [];
        for (i in value) {
            if (value.hasOwnProperty(i) && typeof value[i] !== "function") {
                parts.push(jsonQuote(i) + ":" + toJson(value[i]));
            }
        }
        return "{" + parts.join(",") + "}";
    }
    function writeJson(pathValue, payload) {
        var file = ensureFolder(pathValue);
        file.encoding = "UTF8";
        if (!file.open("w")) {
            throw new Error("Cannot write report: " + file.fsName);
        }
        file.write(toJson(payload));
        file.write("\n");
        file.close();
    }
    function boundsNumbers(layer) {
        var bounds = layer.bounds;
        return [
            Number(bounds[0].as("px")),
            Number(bounds[1].as("px")),
            Number(bounds[2].as("px")),
            Number(bounds[3].as("px"))
        ];
    }
    function moveIntoParent(layer, item) {
        if (item.parent && groups[item.parent]) {
            layer.move(groups[item.parent], ElementPlacement.INSIDE);
        }
    }
    function recordLayer(layer, item) {
        builtLayers.push({
            id: item.id,
            name: layer.name,
            kind: item.kind,
            parent: item.parent || null,
            bounds: item.kind === "group" ? null : boundsNumbers(layer)
        });
    }

    function makeGroup(item) {
        var group = item.parent && groups[item.parent]
            ? groups[item.parent].layerSets.add()
            : app.activeDocument.layerSets.add();
        group.name = item.name || item.id;
        group.visible = item.visible !== false;
        group.opacity = numberValue(item.opacity, 100);
        groups[item.id] = group;
        recordLayer(group, item);
        return group;
    }

    function makeRoundedRectangle(item) {
        var b = item.bounds;
        var left = numberValue(b[0], 0);
        var top = numberValue(b[1], 0);
        var right = numberValue(b[2], 0);
        var bottom = numberValue(b[3], 0);
        var radius = Math.max(0, Math.min(numberValue(item.radius, 0), (right - left) / 2, (bottom - top) / 2));
        var handle = radius * 0.5522847498307936;
        function point(anchor, incoming, outgoing) {
            var pathPoint = new PathPointInfo();
            pathPoint.kind = PointKind.CORNERPOINT;
            pathPoint.anchor = anchor;
            pathPoint.leftDirection = outgoing;
            pathPoint.rightDirection = incoming;
            return pathPoint;
        }
        var points;
        if (radius === 0) {
            points = [
                point([left, top], [left, top], [left, top]),
                point([right, top], [right, top], [right, top]),
                point([right, bottom], [right, bottom], [right, bottom]),
                point([left, bottom], [left, bottom], [left, bottom])
            ];
        } else {
            points = [
                point([left + radius, top], [left + radius - handle, top], [left + radius, top]),
                point([right - radius, top], [right - radius, top], [right - radius + handle, top]),
                point([right, top + radius], [right, top + radius - handle], [right, top + radius]),
                point([right, bottom - radius], [right, bottom - radius], [right, bottom - radius + handle]),
                point([right - radius, bottom], [right - radius + handle, bottom], [right - radius, bottom]),
                point([left + radius, bottom], [left + radius, bottom], [left + radius - handle, bottom]),
                point([left, bottom - radius], [left, bottom - radius + handle], [left, bottom - radius]),
                point([left, top + radius], [left, top + radius], [left, top + radius - handle])
            ];
        }
        var subpath = new SubPathInfo();
        subpath.closed = true;
        subpath.operation = ShapeOperation.SHAPEADD;
        subpath.entireSubPath = points;
        var workPath = app.activeDocument.pathItems.add("__codex_shape_" + item.id, [subpath]);
        workPath.select();

        var descriptor = new ActionDescriptor();
        var reference = new ActionReference();
        reference.putClass(sid("contentLayer"));
        descriptor.putReference(cid("null"), reference);

        var content = new ActionDescriptor();
        var solid = new ActionDescriptor();
        solid.putObject(cid("Clr "), sid("RGBColor"), rgbDescriptor(item.fill || "#000000"));
        content.putObject(cid("Type"), sid("solidColorLayer"), solid);
        descriptor.putObject(cid("Usng"), sid("contentLayer"), content);
        executeAction(cid("Mk  "), descriptor, DialogModes.NO);

        var layer = app.activeDocument.activeLayer;
        layer.name = item.name || item.id;
        layer.opacity = numberValue(item.opacity, 100);
        layer.visible = item.visible !== false;
        if (numberValue(item.rotation, 0) !== 0) {
            layer.rotate(numberValue(item.rotation, 0), AnchorPosition.MIDDLECENTER);
        }
        moveIntoParent(layer, item);
        return layer;
    }

    function makeText(item) {
        var layer = app.activeDocument.artLayers.add();
        layer.kind = LayerKind.TEXT;
        layer.name = item.name || item.id;
        var text = layer.textItem;
        text.kind = item.paragraph ? TextType.PARAGRAPHTEXT : TextType.POINTTEXT;
        text.contents = String(item.text || "");
        if (item.font) { text.font = String(item.font); }
        text.size = px(numberValue(item.size_px, 12));
        text.tracking = numberValue(item.tracking, 0);
        text.color = solidColor(item.fill || "#000000");
        if (item.justification === "center") { text.justification = Justification.CENTER; }
        else if (item.justification === "right") { text.justification = Justification.RIGHT; }
        else { text.justification = Justification.LEFT; }

        var b = item.bounds || [0, 0, 0, 0];
        if (item.paragraph) {
            text.position = [px(b[0]), px(b[1])];
            text.width = px(Math.max(1, b[2] - b[0]));
            text.height = px(Math.max(1, b[3] - b[1]));
        } else {
            var baseline = item.baseline_y !== undefined ? item.baseline_y : b[1] + numberValue(item.size_px, 12);
            text.position = [px(b[0]), px(baseline)];
        }
        layer.opacity = numberValue(item.opacity, 100);
        layer.visible = item.visible !== false;
        if (numberValue(item.rotation, 0) !== 0) {
            layer.rotate(numberValue(item.rotation, 0), AnchorPosition.MIDDLECENTER);
        }
        moveIntoParent(layer, item);
        return layer;
    }

    function placeSmartObject(item) {
        var source = new File(item.source_asset);
        if (!source.exists) {
            throw new Error("Missing smart-object source: " + source.fsName);
        }
        var descriptor = new ActionDescriptor();
        descriptor.putPath(cid("null"), source);
        executeAction(sid("placeEvent"), descriptor, DialogModes.NO);
        var layer = app.activeDocument.activeLayer;
        layer.name = item.name || item.id;

        if (item.bounds && item.bounds.length === 4) {
            var current = boundsNumbers(layer);
            var currentWidth = Math.max(0.001, current[2] - current[0]);
            var currentHeight = Math.max(0.001, current[3] - current[1]);
            var targetWidth = Math.max(0.001, item.bounds[2] - item.bounds[0]);
            var targetHeight = Math.max(0.001, item.bounds[3] - item.bounds[1]);
            if (item.fit !== "none") {
                layer.resize(targetWidth / currentWidth * 100, targetHeight / currentHeight * 100, AnchorPosition.TOPLEFT);
            }
            current = boundsNumbers(layer);
            layer.translate(px(item.bounds[0] - current[0]), px(item.bounds[1] - current[1]));
        }
        if (numberValue(item.rotation, 0) !== 0) {
            layer.rotate(numberValue(item.rotation, 0), AnchorPosition.MIDDLECENTER);
        }
        layer.opacity = numberValue(item.opacity, 100);
        layer.visible = item.visible !== false;
        moveIntoParent(layer, item);
        return layer;
    }

    function putCommonEffectValues(descriptor, effect, defaultMode) {
        descriptor.putBoolean(sid("enabled"), effect.enabled !== false);
        descriptor.putBoolean(sid("present"), true);
        descriptor.putBoolean(sid("showInDialog"), false);
        descriptor.putEnumerated(sid("mode"), sid("blendMode"), sid(effect.blend_mode || defaultMode));
        descriptor.putUnitDouble(sid("opacity"), sid("percentUnit"), numberValue(effect.opacity, 100));
        descriptor.putObject(sid("color"), sid("RGBColor"), rgbDescriptor(effect.color || "#000000"));
    }
    function applyLayerEffects(layer, effects) {
        if (!effects) { return; }
        app.activeDocument.activeLayer = layer;
        var style = new ActionDescriptor();
        style.putUnitDouble(sid("scale"), sid("percentUnit"), 100);

        if (effects.stroke && effects.stroke.enabled !== false) {
            var stroke = new ActionDescriptor();
            putCommonEffectValues(stroke, effects.stroke, "normal");
            var placement = effects.stroke.position || "outside";
            var placementId = placement === "inside" ? "insetFrame" : (placement === "center" ? "centeredFrame" : "outsetFrame");
            stroke.putEnumerated(sid("style"), sid("frameStyle"), sid(placementId));
            stroke.putEnumerated(sid("paintType"), sid("frameFill"), sid("solidColor"));
            stroke.putUnitDouble(sid("size"), sid("pixelsUnit"), numberValue(effects.stroke.size, 1));
            style.putObject(sid("frameFX"), sid("frameFX"), stroke);
        }
        if (effects.drop_shadow && effects.drop_shadow.enabled !== false) {
            var drop = new ActionDescriptor();
            putCommonEffectValues(drop, effects.drop_shadow, "multiply");
            drop.putBoolean(sid("useGlobalAngle"), false);
            drop.putUnitDouble(sid("localLightingAngle"), sid("angleUnit"), numberValue(effects.drop_shadow.angle, 90));
            drop.putUnitDouble(sid("distance"), sid("pixelsUnit"), numberValue(effects.drop_shadow.distance, 0));
            drop.putUnitDouble(sid("chokeMatte"), sid("percentUnit"), numberValue(effects.drop_shadow.spread, 0));
            drop.putUnitDouble(sid("blur"), sid("pixelsUnit"), numberValue(effects.drop_shadow.size, 0));
            drop.putUnitDouble(sid("noise"), sid("percentUnit"), numberValue(effects.drop_shadow.noise, 0));
            style.putObject(sid("dropShadow"), sid("dropShadow"), drop);
        }
        if (effects.inner_shadow && effects.inner_shadow.enabled !== false) {
            var innerShadow = new ActionDescriptor();
            putCommonEffectValues(innerShadow, effects.inner_shadow, "multiply");
            innerShadow.putBoolean(sid("useGlobalAngle"), false);
            innerShadow.putUnitDouble(sid("localLightingAngle"), sid("angleUnit"), numberValue(effects.inner_shadow.angle, 90));
            innerShadow.putUnitDouble(sid("distance"), sid("pixelsUnit"), numberValue(effects.inner_shadow.distance, 0));
            innerShadow.putUnitDouble(sid("chokeMatte"), sid("percentUnit"), numberValue(effects.inner_shadow.choke, 0));
            innerShadow.putUnitDouble(sid("blur"), sid("pixelsUnit"), numberValue(effects.inner_shadow.size, 0));
            style.putObject(sid("innerShadow"), sid("innerShadow"), innerShadow);
        }
        if (effects.inner_glow && effects.inner_glow.enabled !== false) {
            var innerGlow = new ActionDescriptor();
            putCommonEffectValues(innerGlow, effects.inner_glow, "screen");
            innerGlow.putEnumerated(sid("glowTechnique"), sid("glowTechnique"), sid("softMatte"));
            innerGlow.putUnitDouble(sid("chokeMatte"), sid("percentUnit"), numberValue(effects.inner_glow.choke, 0));
            innerGlow.putUnitDouble(sid("blur"), sid("pixelsUnit"), numberValue(effects.inner_glow.size, 0));
            innerGlow.putEnumerated(sid("innerGlowSource"), sid("innerGlowSource"), sid("edgeGlow"));
            style.putObject(sid("innerGlow"), sid("innerGlow"), innerGlow);
        }
        if (effects.bevel_emboss && effects.bevel_emboss.enabled !== false) {
            var bevel = new ActionDescriptor();
            bevel.putBoolean(sid("enabled"), true);
            bevel.putEnumerated(sid("highlightMode"), sid("blendMode"), sid(effects.bevel_emboss.highlight_mode || "screen"));
            bevel.putObject(sid("highlightColor"), sid("RGBColor"), rgbDescriptor(effects.bevel_emboss.highlight_color || "#FFFFFF"));
            bevel.putUnitDouble(sid("highlightOpacity"), sid("percentUnit"), numberValue(effects.bevel_emboss.highlight_opacity, 75));
            bevel.putEnumerated(sid("shadowMode"), sid("blendMode"), sid(effects.bevel_emboss.shadow_mode || "multiply"));
            bevel.putObject(sid("shadowColor"), sid("RGBColor"), rgbDescriptor(effects.bevel_emboss.shadow_color || "#000000"));
            bevel.putUnitDouble(sid("shadowOpacity"), sid("percentUnit"), numberValue(effects.bevel_emboss.shadow_opacity, 75));
            bevel.putEnumerated(sid("bevelStyle"), sid("bevelEmbossStyle"), sid("innerBevel"));
            bevel.putEnumerated(sid("bevelTechnique"), sid("bevelEmbossTechnique"), sid("smooth"));
            bevel.putEnumerated(sid("bevelDirection"), sid("bevelEmbossStampStyle"), sid(effects.bevel_emboss.direction === "down" ? "stampIn" : "stampOut"));
            bevel.putUnitDouble(sid("strengthRatio"), sid("percentUnit"), numberValue(effects.bevel_emboss.depth, 100));
            bevel.putUnitDouble(sid("blur"), sid("pixelsUnit"), numberValue(effects.bevel_emboss.size, 5));
            bevel.putUnitDouble(sid("soften"), sid("pixelsUnit"), numberValue(effects.bevel_emboss.soften, 0));
            bevel.putBoolean(sid("useGlobalAngle"), false);
            bevel.putUnitDouble(sid("localLightingAngle"), sid("angleUnit"), numberValue(effects.bevel_emboss.angle, 120));
            bevel.putUnitDouble(sid("localLightingAltitude"), sid("angleUnit"), numberValue(effects.bevel_emboss.altitude, 30));
            style.putObject(sid("bevelEmboss"), sid("bevelEmboss"), bevel);
        }

        var setDescriptor = new ActionDescriptor();
        var setReference = new ActionReference();
        setReference.putProperty(sid("property"), sid("layerEffects"));
        setReference.putEnumerated(sid("layer"), sid("ordinal"), sid("targetEnum"));
        setDescriptor.putReference(cid("null"), setReference);
        setDescriptor.putObject(cid("T   "), sid("layerEffects"), style);
        executeAction(cid("setd"), setDescriptor, DialogModes.NO);
    }

    function makeLayer(item) {
        var layer;
        if (item.kind === "shape") {
            if (item.shape && item.shape !== "rounded-rectangle") {
                throw new Error("Unsupported native shape: " + item.shape);
            }
            layer = makeRoundedRectangle(item);
        } else if (item.kind === "text") {
            layer = makeText(item);
        } else if (item.kind === "smart-object" || item.kind === "raster-object" || item.kind === "scene") {
            layer = placeSmartObject(item);
        } else {
            throw new Error("Unsupported layer kind: " + item.kind);
        }
        applyLayerEffects(layer, item.effects);
        recordLayer(layer, item);
        return layer;
    }

    function createDocument() {
        var documentJob = JOB.document;
        var document = app.documents.add(
            px(documentJob.width),
            px(documentJob.height),
            numberValue(documentJob.resolution, 72),
            documentJob.name || "codex-psd-job",
            NewDocumentMode.RGB,
            DocumentFill.TRANSPARENT,
            1,
            BitsPerChannelType.EIGHT,
            documentJob.profile || "sRGB IEC61966-2.1"
        );
        ownedDocuments.push(document);
        if (document.artLayers.length === 1 && document.layerSets.length === 0) {
            bootstrapLayer = document.artLayers[0];
        }
        return document;
    }

    function build() {
        var document = createDocument();
        var layers = JOB.layers.slice(0);
        function buildChildren(parentId) {
            var children = [];
            var index;
            for (index = 0; index < layers.length; index += 1) {
                if ((layers[index].parent || null) === parentId) { children.push(layers[index]); }
            }
            children.sort(function (a, b) { return numberValue(a.z, 0) - numberValue(b.z, 0); });
            for (index = 0; index < children.length; index += 1) {
                if (children[index].kind === "group") {
                    makeGroup(children[index]);
                    buildChildren(children[index].id);
                } else {
                    makeLayer(children[index]);
                }
            }
        }
        buildChildren(null);
        if (builtLayers.length !== layers.length) {
            throw new Error("Group parent cycle or unreachable layer parent");
        }
        if (bootstrapLayer) {
            bootstrapLayer.remove();
            bootstrapLayer = null;
        }

        var psdFile = ensureFolder(JOB.output.psd);
        var psdOptions = new PhotoshopSaveOptions();
        psdOptions.layers = true;
        psdOptions.embedColorProfile = true;
        document.saveAs(psdFile, psdOptions, true, Extension.LOWERCASE);
        document.close(SaveOptions.DONOTSAVECHANGES);
        ownedDocuments.pop();

        var reopened = app.open(psdFile);
        ownedDocuments.push(reopened);
        var previewDocument = reopened.duplicate("codex-preview", true);
        ownedDocuments.push(previewDocument);
        previewDocument.flatten();
        var pngOptions = new PNGSaveOptions();
        pngOptions.compression = 9;
        previewDocument.saveAs(ensureFolder(JOB.output.preview), pngOptions, true, Extension.LOWERCASE);
        previewDocument.close(SaveOptions.DONOTSAVECHANGES);
        ownedDocuments.pop();

        var scenePreviewFile = null;
        if (JOB.output.scene_preview) {
            var sceneGroupName = null;
            var sceneIndex;
            for (sceneIndex = 0; sceneIndex < JOB.layers.length; sceneIndex += 1) {
                if (JOB.layers[sceneIndex].id === JOB.scene_group_id) {
                    sceneGroupName = JOB.layers[sceneIndex].name || JOB.layers[sceneIndex].id;
                    break;
                }
            }
            if (!sceneGroupName) {
                throw new Error("Cannot resolve scene_group_id: " + JOB.scene_group_id);
            }
            var sceneDocument = reopened.duplicate("codex-scene-preview", false);
            ownedDocuments.push(sceneDocument);
            var foundSceneGroup = false;
            for (sceneIndex = 0; sceneIndex < sceneDocument.layers.length; sceneIndex += 1) {
                var topLayer = sceneDocument.layers[sceneIndex];
                var isTargetGroup = topLayer.typename === "LayerSet" && topLayer.name === sceneGroupName;
                topLayer.visible = isTargetGroup;
                if (isTargetGroup) { foundSceneGroup = true; }
            }
            if (!foundSceneGroup) {
                throw new Error("Scene group is missing after reopen: " + sceneGroupName);
            }
            sceneDocument.flatten();
            scenePreviewFile = ensureFolder(JOB.output.scene_preview);
            sceneDocument.saveAs(scenePreviewFile, pngOptions, true, Extension.LOWERCASE);
            sceneDocument.close(SaveOptions.DONOTSAVECHANGES);
            ownedDocuments.pop();
        }
        reopened.close(SaveOptions.DONOTSAVECHANGES);
        ownedDocuments.pop();

        var preservation = verifyInitialDocuments();
        if (!preservation.preserved) {
            var preservationError = new Error("A document that was open before the Photoshop job is no longer open");
            preservationError.codexCode = "E_PREEXISTING_DOCUMENT_CLOSED";
            preservationError.preservation = preservation;
            throw preservationError;
        }

        var report = {
            status: "ok",
            code: "OK",
            psd: psdFile.fsName,
            preview: new File(JOB.output.preview).fsName,
            scene_preview: scenePreviewFile ? scenePreviewFile.fsName : null,
            save_close_reopen_verified: true,
            preexisting_documents: preservation,
            layers: builtLayers
        };
        writeJson(JOB.output.report, report);
        return report;
    }

    app.displayDialogs = DialogModes.NO;
    captureInitialDocuments();
    try {
        var result = build();
        if (originalDocument) { app.activeDocument = originalDocument; }
        app.displayDialogs = originalDialogs;
        return toJson(result);
    } catch (error) {
        while (ownedDocuments.length) {
            try { ownedDocuments.pop().close(SaveOptions.DONOTSAVECHANGES); } catch (ignored) {}
        }
        if (originalDocument) {
            try { app.activeDocument = originalDocument; } catch (ignoredRestore) {}
        }
        app.displayDialogs = originalDialogs;
        var failure = {
            status: "error",
            code: error.codexCode || "E_PHOTOSHOP_SCRIPT",
            message: String(error),
            line: error.line || null,
            preexisting_documents: error.preservation || verifyInitialDocuments()
        };
        try { writeJson(JOB.output.report, failure); } catch (ignoredReport) {}
        throw error;
    }
}());
