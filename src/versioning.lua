local versioning = {}

versioning.supportedVersion = { 1, 1, 0 } -- Major, Minor, Patch

function versioning:isSupportedVersion(versionString: string): boolean
	local sanitizedVersionString = string.gsub(versionString, "[^0-9.]", "")
	for i, v in string.split(sanitizedVersionString, ".") do
		if tonumber(v) > self.supportedVersion[i] then
			return false
		end
	end
	return true
end

return versioning
