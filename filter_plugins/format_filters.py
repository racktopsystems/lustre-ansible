from typing import Dict


class FilterModule:
    @staticmethod
    def convert_dict_of_lists_to_generator(map: Dict):
        for k, v in map.items():
            for ds in v:
                yield k + "/" + ds

    def fmt_confd_peer_iface_incl_list(self, iface: str):
        """Trims trailing digits from an interface name and formats a string
        that represents a list of peer interfaces in the confd config file.
        """
        end = len(iface)
        for i in range(len(iface) - 1, -1, -1):
            if iface[i].isalpha():
                break
            end = i
        # This should look something like: ["^(admin*)"]
        return f'["^({iface[:end]}*)"]'

    def filters(self):
        return {
            "mntpnt_map_to_list": self.convert_dict_of_lists_to_generator,
            "fmt_confd_peer_iface_incl_list": self.fmt_confd_peer_iface_incl_list,
        }
