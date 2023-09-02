from collections import namedtuple, defaultdict
from typing import List
import ipywidgets as wgs
import html


default_config = dict(
    max_key_length = 50,
    max_value_length = 50,
    item_general_style = 'display:inline; font-family: monospace; font-size: 14px',
    item_active_style = 'background-color:yellow;',
    item_not_active_style = '',
    indent = '&nbsp; &nbsp;',
)


"""
The struct that is used to store the formatted JSON lines.
level - the nesting level of the line object inside the JSON. 
    The level is used to calculate indents while printing.
obj_name - the key of the line object inside the JSON.
    The obj_name is None if the line object is inside a list.
obj_value - the value of the line object. It is used for the leaves only.
    The obj_value is None for nested dictionaries and lists.
text - the formatted line that is ready to be printed.
path - the full path to the object inside the JSON.
"""
json_line_struct = namedtuple(
    'json_line_struct',
    field_names=['level', 'obj_name', 'obj_value', 'text', 'path']
)

class JsonFormatter:
    """The class parses JSON object and converts it into printable form."""
    
    def __init__(self, max_key_length, max_value_length):
        """
        Constructor.
        
        max_key_length - the maximum length of an object key when printed.
        max_value_length - the maximum length of an object value when printed.
        """
        self.max_key_length = max_key_length
        self.max_value_length = max_value_length
        
    
    def _draw_json(self, obj, result=None, obj_name=None, level=0, path=None):
        if not result:
            result = []
        if not path:
            path = ()

        if isinstance(obj, dict):
            if not obj_name:
                result.append(
                    json_line_struct(level, None, None, '{', path)
                )
            else:
                result.append(
                    json_line_struct(
                        level, 
                        obj_name, 
                        None, 
                        f'"{obj_name[:self.max_key_length]}"' + ": {", 
                        path
                    )
                )
            for k, v in obj.items():
                subresult = self._draw_json(v, result, k, level+1, path + (k, ))
            result.append(json_line_struct(level, None, None, '},', None))

        elif isinstance(obj, list):
            if not obj_name:
                result.append(json_line_struct(level, None, None, '[', path))
            else:
                result.append(
                    json_line_struct(
                        level, 
                        obj_name,
                        None, 
                        f'"{obj_name[:self.max_key_length]}": [', 
                        path
                    )
                )
            for i, v in enumerate(obj):
                subresult = self._draw_json(v, result, None, level+1, path + (i, ))
            result.append(json_line_struct(level, None, None, '],', None))

        else:
            if isinstance(obj, str):
                obj_print = f'"{obj[:self.max_value_length]}"'
            else:
                obj_print = f'{obj}'[:self.max_value_length]
            if obj_name:
                result.append(
                    json_line_struct(
                        level, 
                        obj_name, 
                        obj, 
                        f'"{obj_name[:self.max_key_length]}": {obj_print},', 
                        path
                    )
                )
            else:
                result.append(json_line_struct(level, None, obj, f'{obj_print},', path))

        return result
    
    def draw_json(self, obj: dict) -> List[json_line_struct]:
        """
        Parses the JSON object and converts it into lines ready to be printed.
        """
        result = []
        return self._draw_json(obj, result)
    
    
    def print_json(self, obj: dict):
        """Prints the formatted JSON object."""
        
        tuples = self.draw_json(obj)
        for t in tuples:
            print('  ' * t.level + t.text)
            
            
class PandasSimpleCodeGenerator:
    """
    The simple JSON parser generator for Pandas.
    It generates a full value extracting statement from the JSON root to the value 
    for each value.
    """
    
    def __init__(self, source_series, target_df):
        self.source_series = source_series
        self.target_df = target_df


    def _form_pandas_line(self, path):
        target_subname = str(path[-1])
        if isinstance(path[-1], int) and len(path) > 1:
            target_subname = f'{path[-2]}_{target_subname}'

        self.names[target_subname] += 1
        if self.names[target_subname] > 1:
            target_subname = f'{target_subname}_{self.names[target_subname]}'
        val = f"{self.target_df}['{target_subname}'] = {self.source_series}"
        for p in path:
            val += f".str[{p.__repr__()}]"
        return val


    def generate(self, paths):
        self.names = defaultdict(int)
        result = [self._form_pandas_line(path) for path in paths]
        return '\n'.join(result)
    
    
class ComplexCodeGenerator:
    
    def _convert_paths_to_dict(self, paths):
        root = {}
        for path in paths:
            prev = root
            for i, item in enumerate(path, 1):
                if prev.get(item) is None:
                    prev[item] = {}
                prev = prev[item]
            prev['$__save_item'] = True
        return root

    def _step(self, obj, path=()):
        if (len(obj) == 1 and not obj.get('$__save_item')):
            if not path:
                self.names_count += 1
                self.result[f'###{self.names_count}'] = path
                self.named_paths[path] = (f'###{self.names_count}',)
            key = list(obj.keys())[0]
            if not obj[key]:
                self.names_count += 1
                self.result[f'###{self.names_count}'] = self.named_paths.get(path, path) + (key,)
            else:
                self._step(obj[key], self.named_paths.get(path, path) + (key,))
        else:
            self.names_count += 1
            self.result[f'###{self.names_count}'] = path
            self.named_paths[path] = (f'###{self.names_count}',)
            for k, v in obj.items():
                if k != '$__save_item':
                    self._step(v, self.named_paths.get(path, path) + (k,))

    def _rename_stub_names(self, paths, root_name):
        renames = {'###1': root_name}
        new_paths = {}

        for k, path in list(paths.items())[1:]:
            new_name = path[-1]
            last_added = -1
            while True:
                if new_name not in renames.values() and not isinstance(path[last_added], int):
                    break
                if -last_added == len(path):
                    break
                last_added -= 1
                new_name = f'{renames.get(path[last_added], path[last_added])}_{new_name}'
            renames[k] = new_name
            new_paths[new_name] = (renames[path[0]],) + path[1:]  
        return new_paths


    def run(self, paths, root_name=''):
        obj = self._convert_paths_to_dict(paths)
        self.result = {}
        self.named_paths = {}
        self.names_count = 0
        self._step(obj)
        return self._rename_stub_names(self.result, root_name)
    
    
class PandasComplexCodeGenerator:
    """
    The complex JSON parser generator for Pandas.
    It extracts the intermediate object into Pandas columns if the object
    is in more than two full extracting paths.
    """
    
    def __init__(self, source_series, target_df):
        self.source_series = source_series
        self.target_df = target_df
        self.code_generator = ComplexCodeGenerator()


    def _form_pandas_line(self, target, source):
        target_part = f"{self.target_df}['{target}']"
        if source[0] == '':
            source_part = self.source_series
        else:
            source_part = f"{self.target_df}['{source[0]}']"
        for part in source[1:]:
            source_part = f"{source_part}.str[{part.__repr__()}]"
        
        return f'{target_part} = {source_part}'


    def generate(self, paths):
        result = []
        gen_paths = self.code_generator.run(paths)
        for target, source in gen_paths.items():
            result.append(self._form_pandas_line(target, source))
        return '\n'.join(result)
    
    
class ParserGenerator:
    
    def __init__(self, config: dict = None):
        if config is None:
            self.config = default_config
        
        self.formatter = JsonFormatter(
            self.config['max_key_length'],
            self.config['max_value_length']
        )

        
    def _format_json_line(self, line: json_line_struct, is_active: bool = False) -> str:
        indent = self.config['indent'] * line.level
        general_style = self.config['item_general_style']
        if is_active:
            activity_style = self.config['item_active_style']
        else:
            activity_style = self.config['item_not_active_style']
        
        text = html.escape(line.text)
        
        return f'<div style="{activity_style} {general_style}">{indent}{text}</div>'

    
    def _on_json_button_click(self, info):
        json_line_wg = self.button_jsonwgs_map[info['owner']]
        json_line = self.button_linestruct_map[info['owner']]
        if info['new']:
            json_line_wg.value = self._format_json_line(json_line, is_active=True)
        else:
            json_line_wg.value = self._format_json_line(json_line, is_active=False)
        
        
    def run(self, json_obj):
        json_lines = self.formatter.draw_json(json_obj)
        
        self.json_line_wgs = []
        self.json_button_wgs = []
        self.button_linestruct_map = {}
        self.button_jsonwgs_map = {}
        for json_line in json_lines:
            json_line_wg = wgs.HTML(
                self._format_json_line(json_line)
            )
            json_line_wg.layout.height = '20px'
            json_line_wg.layout.margin = f'0 0 0 0'
            self.json_line_wgs.append(json_line_wg)

            if json_line.path:
                button = wgs.ToggleButton()
                button.observe(self._on_json_button_click, 'value')
                button.layout.height = '20px'
                self.json_button_wgs.append(button)
                self.button_linestruct_map[button] = json_line
                self.button_jsonwgs_map[button] = json_line_wg
            else:
                label = wgs.Label()
                label.layout.height = '20px'
                self.json_button_wgs.append(label)
                
        
        json_line_box = wgs.VBox(self.json_line_wgs)
        json_button_box = wgs.VBox(self.json_button_wgs)
        json_box = wgs.HBox([json_button_box, json_line_box])
        json_box.layout.height = f'{len(self.json_line_wgs)*20}px'
        self.json_box = json_box
        display(json_box)


        source_label = wgs.Label(value='Source pd.Series: ')
        self.source_text = wgs.Text(value="df['log']")
        display(wgs.HBox([source_label, self.source_text]))

        target_label = wgs.Label(value='Target pd.DataFrame: ')
        self.target_text = wgs.Text(value="df")
        display(wgs.HBox([target_label, self.target_text]))

        self.simple_generate_button = wgs.Button(description='Generate (Simple Generator)')
        self.simple_generate_button.on_click(self._on_click_generate)
        
        self.complex_generate_button = wgs.Button(description='Generate (Complex Generator)')
        self.complex_generate_button.on_click(self._on_click_generate)
        display(wgs.HBox([self.simple_generate_button, self.complex_generate_button]))

        self.result_output = wgs.Textarea()
        self.result_output.layout.width = '800px'
        self.result_output.layout.height = '200px'
        display(self.result_output)


    def _on_click_generate(self, button):
        paths = []
        for json_button, json_line in self.button_linestruct_map.items():
            if json_button.value:
                paths.append(json_line.path)
        
        if button == self.simple_generate_button:
            generator = PandasSimpleCodeGenerator(self.source_text.value, self.target_text.value)
        elif button == self.complex_generate_button:
            generator = PandasComplexCodeGenerator(self.source_text.value, self.target_text.value)
        self.result_output.value = generator.generate(paths)
