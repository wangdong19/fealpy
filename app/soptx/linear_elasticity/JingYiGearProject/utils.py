def export_to_inp(filename, nodes, elements, fixed_nodes, load_nodes, loads, young_modulus, poisson_ratio, density, used_app='abaqus', mesh_type='hex'):
    """
    齿轮专用的，相关信息导出为 Abaqus 的 inp 文件
    :param filename: 文件名
    :param nodes: 网格节点
    :param elements: 网格单元
    :param fixed_nodes: 固定点索引
    :param load_nodes: 载荷点索引
    :param loads: 载荷点载荷
    :param young_modulus: 杨氏模量（GP）
    :param poisson_ratio: 泊松比
    :param density: 密度
    :param used_app: 使用的有限元软件，默认为 Abaqus
    :param mesh_type: 网格类型，默认为六面体网格（hex），可选四面体网格（tet）
    :return:
    """
    assert used_app in ['abaqus', 'ansys']
    assert mesh_type in ['hex', 'tet']
    if used_app == 'abaqus':
        export_to_inp_abaqus(filename, nodes, elements, fixed_nodes, load_nodes, loads, young_modulus, poisson_ratio, density, mesh_type)
    elif used_app == 'ansys':
        export_to_inp_ansys(filename, nodes, elements, fixed_nodes, load_nodes, loads, young_modulus, poisson_ratio, density, mesh_type)
    else:
        raise ValueError("Invalid used_app parameter!")

def export_to_inp_abaqus(filename, nodes, elements, fixed_nodes, load_nodes, loads, young_modulus, poisson_ratio, density, mesh_type='hex'):
    """
    齿轮专用的，相关信息导出为 Abaqus 的 inp 文件
    :param filename: 文件名
    :param nodes: 网格节点
    :param elements: 网格单元
    :param fixed_nodes: 固定点索引
    :param load_nodes: 载荷点索引
    :param loads: 载荷点载荷
    :param young_modulus: 杨氏模量（GP）
    :param poisson_ratio: 泊松比
    :param density: 密度
    :param mesh_type: 网格类型，默认为六面体网格（hex），可选四面体网格（tet）
    :return:
    """
    with open(filename, 'w') as file:
        file.write("*Heading\n** Generated by Custom Export Script\n*Preprint, echo=NO, model=NO, history=NO, contact=NO\n")
        file.write("*Part, name=Gear\n")
        file.write("*Node\n")

        elements = elements+1
        fixed_nodes = fixed_nodes+1
        load_nodes = load_nodes+1
        # 写入节点信息
        for i, node in enumerate(nodes):
            file.write(f"{i+1}, {node[0]}, {node[1]}, {node[2]}\n")

        # 写入单元信息
        if mesh_type == 'hex':  # 六面体网格
            file.write("*Element, type=C3D8, elset=AllElements\n")
            for i, elem in enumerate(elements):
                file.write(
                    f"{i + 1}, {elem[0]}, {elem[1]}, {elem[2]}, {elem[3]}, {elem[4]}, {elem[5]}, {elem[6]}, {elem[7]}\n")
        elif mesh_type == 'tet':  # 四面体网格
            file.write("*Element, type=C3D4, elset=AllElements\n")
            for i, elem in enumerate(elements):
                file.write(f"{i + 1}, {elem[0]}, {elem[1]}, {elem[2]}, {elem[3]}\n")

        # 写入截面
        file.write("*Solid Section, elset=AllElements, material=Steel\n")
        file.write("*End Part\n**\n")

        # 定义装配和实例
        file.write("*Assembly, name=Assembly\n*Instance, name=GearInstance, part=Gear\n*End Instance\n")

        # 定义固定节点集
        file.write("*Nset, nset=FixedNodes, instance=GearInstance\n")
        for i in range(0, len(fixed_nodes), 16):
            file.write(", ".join(str(node) for node in fixed_nodes[i:i + 16]) + ",\n")

        # 定义载荷节点集
        file.write("*Nset, nset=LoadNodes, instance=GearInstance\n")
        for i in range(0, len(load_nodes), 16):
            file.write(", ".join(str(node) for node in load_nodes[i:i + 16]) + ",\n")
        file.write("*End Assembly\n")

        # 写入材料信息
        file.write("*Material, name=Steel\n")
        file.write(f"*Density\n{density}\n")
        file.write(f"*Elastic\n{young_modulus}, {poisson_ratio}\n")

        # 写入步骤、边界条件和载荷
        file.write("** STEP: LoadStep\n*Step, name=LoadStep, nlgeom=NO\n*Static\n1., 1., 1e-05, 1.\n")

        # 固定边界条件
        file.write("*Boundary\nFixedNodes, ENCASTRE\n")

        # 施加集中载荷
        file.write(f"*Cload\n")
        for i, load_node in enumerate(load_nodes):
            node_id = load_node
            forces = loads[i]
            file.write(f"GearInstance.{node_id}, 1, {forces[0]}\n")
            file.write(f"GearInstance.{node_id}, 2, {forces[1]}\n")
            file.write(f"GearInstance.{node_id}, 3, {forces[2]}\n")

        file.write("*Output, field, variable=PRESELECT\n")
        file.write("*Output, history, variable=PRESELECT\n")
        file.write("*End Step\n")
        file.write("** Output Global Stiffness Matrix\n")
        file.write("*Step, name=Global_Stiffness_Matrix\n")
        file.write("*MATRIX GENERATE, STIFFNESS, element by element\n")
        file.write("*MATRIX OUTPUT, STIFFNESS, FORMAT=COORDINATE\n")
        file.write("*End Step\n")

        print("Export to inp file successfully!")

def export_to_inp_ansys(filename, nodes, elements, fixed_nodes, load_nodes, loads, young_modulus, poisson_ratio, density, mesh_type='hex'):
    """
        齿轮专用的，相关信息导出为 Abaqus 的 inp 文件
        :param filename: 文件名
        :param nodes: 网格节点
        :param elements: 网格单元
        :param fixed_nodes: 固定点索引
        :param load_nodes: 载荷点索引
        :param loads: 载荷点载荷
        :param young_modulus: 杨氏模量（GP）
        :param poisson_ratio: 泊松比
        :param density: 密度
        :param mesh_type: 网格类型，默认为六面体网格（hex），可选四面体网格（tet）
        :return:
        """
    with open(filename, 'w') as file:
        file.write(
            "*Heading\n** Generated by Custom Export Script\n*Preprint, echo=NO, model=NO, history=NO, contact=NO\n")
        file.write("*Node\n")

        elements = elements + 1
        fixed_nodes = fixed_nodes + 1
        load_nodes = load_nodes + 1
        # 写入节点信息
        for i, node in enumerate(nodes):
            file.write(f"{i + 1}, {node[0]}, {node[1]}, {node[2]}\n")

        # 写入单元信息
        if mesh_type == 'hex':  # 六面体网格
            file.write("*Element, type=C3D8, elset=AllElements\n")
            for i, elem in enumerate(elements):
                file.write(
                    f"{i + 1}, {elem[0]}, {elem[1]}, {elem[2]}, {elem[3]}, {elem[4]}, {elem[5]}, {elem[6]}, {elem[7]}\n")
        elif mesh_type == 'tet':  # 四面体网格
            file.write("*Element, type=C3D4, elset=AllElements\n")
            for i, elem in enumerate(elements):
                file.write(f"{i + 1}, {elem[0]}, {elem[1]}, {elem[2]}, {elem[3]}\n")

        # 定义固定节点集
        file.write("*Nset, nset=FixedNodes\n")
        for i in range(0, len(fixed_nodes), 16):
            file.write(", ".join(str(node) for node in fixed_nodes[i:i + 16]) + ",\n")

        # 定义载荷节点集
        file.write("*Nset, nset=LoadNodes\n")
        for i in range(0, len(load_nodes), 16):
            file.write(", ".join(str(node) for node in load_nodes[i:i + 16]) + ",\n")

        # 写入材料信息
        file.write("*Material, name=Steel\n")
        file.write(f"*Density\n{density}\n")
        file.write(f"*Elastic\n{young_modulus}, {poisson_ratio}\n")

        # 写入截面
        file.write("*Solid Section, elset=AllElements, material=Steel\n")
        file.write(",\n")
        file.write("*End Part\n**\n")
        file.write("*End Assembly\n")

        # 写入步骤、边界条件和载荷
        file.write("** STEP: LoadStep\n*Step, name=LoadStep, nlgeom=NO\n*Static\n1., 1., 1e-05, 1.\n")

        # 固定边界条件
        file.write("*Boundary\nFixedNodes, ENCASTRE\n")

        # 施加集中载荷
        file.write(f"*Cload\n")
        for i, load_node in enumerate(load_nodes):
            node_id = load_node
            forces = loads[i]
            if forces[0] != 0:
                file.write(f"{node_id}, 1, {forces[0]}\n")
            if forces[1] != 0:
                file.write(f"{node_id}, 2, {forces[1]}\n")
            if forces[2] != 0:
                file.write(f"{node_id}, 3, {forces[2]}\n")

        file.write("*End Step\n")

        print("Export to inp file successfully!")