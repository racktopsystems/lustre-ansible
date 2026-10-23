from typing import Dict


class FilterModule:
    @staticmethod
    def convert_dict_of_lists_to_generator(map: Dict):
        for k, v in map.items():
            for ds in v:
                yield k + "/" + ds

    def filters(self):
        return {
            "mntpnt_map_to_list": self.convert_dict_of_lists_to_generator,
        }
