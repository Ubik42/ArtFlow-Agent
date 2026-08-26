#include <rapidjson/document.h>

#include <cctype>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <string>

namespace {

bool IsPortablePackagePath(const std::string& value) {
    if (value.empty() || std::isspace(static_cast<unsigned char>(value.front())) != 0 ||
        std::isspace(static_cast<unsigned char>(value.back())) != 0 || value.front() == '/' ||
        value.front() == '\\' || (value.size() > 1 && value[1] == ':')) {
        return false;
    }
    std::string segment;
    for (const char character : value) {
        if (character == '/' || character == '\\') {
            if (segment == "..") {
                return false;
            }
            segment.clear();
        } else {
            segment.push_back(character);
        }
    }
    return segment != "..";
}

bool IsLowerHexSha256(const rapidjson::Value& value) {
    if (!value.IsString() || value.GetStringLength() != 64) {
        return false;
    }
    for (const char* cursor = value.GetString(); *cursor != '\0'; ++cursor) {
        if (!std::isdigit(static_cast<unsigned char>(*cursor)) && (*cursor < 'a' || *cursor > 'f')) {
            return false;
        }
    }
    return true;
}

bool ValidatePackage(const rapidjson::Document& document, std::string& error) {
    if (!document.IsObject() || !document.HasMember("schema_id") ||
        !document["schema_id"].IsString() ||
        std::string(document["schema_id"].GetString()) != "scene-constraint-package/1") {
        error = "unsupported schema_id";
        return false;
    }

    if (!document.HasMember("camera") || !document["camera"].IsObject()) {
        error = "camera is required";
        return false;
    }
    const auto& camera = document["camera"];
    if (!camera.HasMember("world_transform") || !camera["world_transform"].IsArray() ||
        camera["world_transform"].Size() != 16 || !camera.HasMember("near_clip") ||
        !camera["near_clip"].IsNumber() || !camera.HasMember("far_clip") ||
        !camera["far_clip"].IsNumber() ||
        camera["near_clip"].GetDouble() >= camera["far_clip"].GetDouble()) {
        error = "invalid camera transform or clip range";
        return false;
    }
    if (!camera.HasMember("projection") || !camera["projection"].IsString()) {
        error = "camera projection is required";
        return false;
    }
    const std::string projection = camera["projection"].GetString();
    if ((projection == "perspective" && !camera.HasMember("horizontal_fov_degrees")) ||
        (projection == "orthographic" && !camera.HasMember("ortho_width")) ||
        (projection != "perspective" && projection != "orthographic")) {
        error = "projection-specific camera field is missing";
        return false;
    }

    if (!document.HasMember("passes") || !document["passes"].IsArray()) {
        error = "passes are required";
        return false;
    }
    const std::set<std::string> required = {"beauty", "depth", "world_normal", "object_id"};
    std::set<std::string> kinds;
    for (const auto& pass : document["passes"].GetArray()) {
        if (!pass.IsObject() || !pass.HasMember("kind") || !pass["kind"].IsString() ||
            !pass.HasMember("artifact") || !pass["artifact"].IsObject()) {
            error = "invalid render pass";
            return false;
        }
        const std::string kind = pass["kind"].GetString();
        if (!kinds.insert(kind).second) {
            error = "duplicate render pass kind";
            return false;
        }
        const auto& artifact = pass["artifact"];
        if (!artifact.HasMember("path") || !artifact["path"].IsString() ||
            !IsPortablePackagePath(artifact["path"].GetString()) || !artifact.HasMember("sha256") ||
            !IsLowerHexSha256(artifact["sha256"])) {
            error = "invalid render pass artifact";
            return false;
        }
    }
    for (const auto& kind : required) {
        if (kinds.count(kind) == 0) {
            error = "missing required render pass: " + kind;
            return false;
        }
    }

    if (document.HasMember("regions")) {
        if (!document["regions"].IsArray()) {
            error = "regions must be an array";
            return false;
        }
        std::set<std::string> region_ids;
        for (const auto& region : document["regions"].GetArray()) {
            if (!region.IsObject() || !region.HasMember("region_id") ||
                !region["region_id"].IsString() ||
                !region_ids.insert(region["region_id"].GetString()).second) {
                error = "invalid or duplicate region_id";
                return false;
            }
        }
    }
    return true;
}

int ExpectInvalid(const rapidjson::Document& document, const char* label) {
    std::string error;
    if (ValidatePackage(document, error)) {
        std::cerr << label << " unexpectedly passed\n";
        return 1;
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: scene_constraint_fixture <scene-package.json>\n";
        return 2;
    }
    std::ifstream input(argv[1], std::ios::binary);
    const std::string json((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    rapidjson::Document document;
    document.Parse(json.c_str());
    if (document.HasParseError()) {
        std::cerr << "fixture JSON could not be parsed\n";
        return 3;
    }

    std::string error;
    if (!ValidatePackage(document, error)) {
        std::cerr << "fixture validation failed: " << error << '\n';
        return 4;
    }

    auto& allocator = document.GetAllocator();
    auto& path = document["passes"][0]["artifact"]["path"];
    const std::string original_path = path.GetString();
    path.SetString("../outside.png", allocator);
    if (ExpectInvalid(document, "path traversal") != 0) {
        return 5;
    }
    path.SetString(original_path.c_str(), static_cast<rapidjson::SizeType>(original_path.size()), allocator);

    auto& last_kind = document["passes"][document["passes"].Size() - 1]["kind"];
    const std::string original_kind = last_kind.GetString();
    last_kind.SetString(document["passes"][0]["kind"].GetString(), allocator);
    if (ExpectInvalid(document, "duplicate pass") != 0) {
        return 6;
    }
    last_kind.SetString(original_kind.c_str(), static_cast<rapidjson::SizeType>(original_kind.size()), allocator);

    document["passes"].PopBack();
    if (ExpectInvalid(document, "missing required pass") != 0) {
        return 7;
    }

    std::cout << "Unreal-side C++ contract verification passed.\n";
    return 0;
}
