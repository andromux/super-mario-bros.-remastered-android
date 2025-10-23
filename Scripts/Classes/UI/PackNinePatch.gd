class_name PackNinePatch
extends NinePatchRect

@onready var resource_getter = ResourceGetter.new()

func _ready() -> void:
	update()
	Global.level_theme_changed.connect(update)

func update() -> void:
	if Global.campaign_is_dummy:
		return
	texture = resource_getter.get_resource(texture)
