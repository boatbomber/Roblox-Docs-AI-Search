local Util = {}

function Util.stripString(str: string): string
	return string.gsub(str, "^%s*(.-)%s*$", "%1")
end

return Util
