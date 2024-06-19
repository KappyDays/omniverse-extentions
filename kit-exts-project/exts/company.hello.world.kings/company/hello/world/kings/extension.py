import omni.ext
import omni.ui as ui
import omni.kit.commands

# Functions and vars are available to other extension as usual in python: `example.python_ext.some_public_function(x)`
def some_public_function(x: int):
    print("[company.hello.world.kings] some_public_function was called with x: ", x)
    return x ** x


# Any class derived from `omni.ext.IExt` in top level module (defined in `python.modules` of `extension.toml`) will be
# instantiated when extension gets enabled and `on_startup(ext_id)` will be called. Later when extension gets disabled
# on_shutdown() is called.
class CompanyHelloWorldKingsExtension(omni.ext.IExt):
    # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # this extension is located on filesystem.
    def on_startup(self, ext_id):
        print("[company.hello.world.kings] company hello world kings startup")

        self._count = 0

        self._window = ui.Window("My Window", width=300, height=300)
        with self._window.frame:
            with ui.VStack():
                label = ui.Label("")


                def on_click():
                    self._count += 1
                    label.text = f"count: {self._count}"

                def on_reset():
                    self._count = 0
                    label.text = "empty"
                    
                def capsule():
                    omni.kit.commands.execute('CreatePrimWithDefaultXform',
                        prim_type='Capsule',
                        attributes={'radius': 25.0, 'height': 50.0})           
                             
                def move_capsule():
                    omni.kit.commands.execute('TransformMultiPrimsSRTCpp',
                        count=1,
                        paths=['/World/Capsule'],
                        new_translations=[-9.16221651615987, 12.32924497663775, -8.366366602089109],
                        new_rotation_eulers=[0.0, 0.0, 0.0],
                        new_rotation_orders=[0, 1, 2],
                        new_scales=[1.0, 1.0, 1.0],
                        old_translations=[-9.16221651615987, -9.438819064122114, -8.366366602089109],
                        old_rotation_eulers=[0.0, 0.0, 0.0],
                        old_rotation_orders=[0, 1, 2],
                        old_scales=[1.0, 1.0, 1.0],
                        usd_context_name='',
                        time_code=0.0)         
                              
                on_reset()

                with ui.HStack():
                    ui.Button("Add", clicked_fn=on_click)
                    ui.Button("Capsule", clicked_fn=capsule)
                    ui.Button("Move_Capsule", clicked_fn=move_capsule)
                    ui.Button("Reset", clicked_fn=on_reset)





    def on_shutdown(self):
        print("[company.hello.world.kings] company hello world kings shutdown")
