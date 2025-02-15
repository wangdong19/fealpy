from fealpy.backend import backend_manager as bm
from typing import Any, Union ,Optional
from fealpy.typing import TensorLike
from fealpy.mesh import TriangleMesh
from fealpy.mesh import TetrahedronMesh
from fealpy.mesh import IntervalMesh
from fealpy.mesh import TriangleMesh as TM
from fealpy.mesh import TetrahedronMesh as THM
from fealpy.functionspace import LagrangeFESpace
from fealpy.fem import (BilinearForm 
                        ,ScalarDiffusionIntegrator
                        ,LinearForm
                        ,ScalarSourceIntegrator
                        ,DirichletBC)
from scipy.sparse.linalg import spsolve
from scipy.sparse.linalg import spsolve as spsolve1
from scipy.integrate import solve_ivp
from scipy.sparse import csr_matrix,spdiags,block_diag,bmat
from sympy import *


class LogicMesh():
    def __init__(self , mesh: Union[TriangleMesh,TetrahedronMesh],
                        Vertex_idx : TensorLike,
                        Bdinnernode_idx : TensorLike,
                        Arrisnode_idx : Optional[TensorLike] = None,
                        sort_BdNode_idx : Optional[TensorLike] = None) -> None:
        """
        @param mesh:  物理网格
        @param Vertex_idx : 角点全局编号
        @param Bdinnernode_idx : 面内点全局编号
        @param Arrisnode_idx : 棱内点全局编号
        @param sort_BdNode_idx : 排序后的边界点全局编号
        """
        self.mesh = mesh
        self.TD = mesh.top_dimension()
        self.node = mesh.entity('node')
        self.cell = mesh.entity('cell')
        self.edge = mesh.entity('edge')
        
        self.BdNodeidx = mesh.boundary_node_index()
        self.BdFaceidx = mesh.boundary_face_index()
        self.Vertex_idx = Vertex_idx
        self.Bdinnernode_idx = Bdinnernode_idx
        self.sort_BdNode_idx = sort_BdNode_idx

        self.logic_mesh = self.get_logic_mesh()
        self.logic_node = self.logic_mesh.entity('node')
        self.isconvex = self.is_convex()
        # 新网格下没有该方法
        if self.TD == 2:
            self.node2edge = TM(self.node, self.cell).ds.node_to_edge()
            self.Bi_Lnode_normal = self.get_normal_information(self.logic_mesh)
            self.Bi_Pnode_normal = self.get_normal_information(self.mesh)

        if self.TD == 3:
            if Arrisnode_idx is None:
                raise ValueError('TD = 3, you must give the Arrisnode_idx')
            self.Arrisnode_idx = Arrisnode_idx
            self.Bi_Lnode_normal, self.Ar_Lnode_normal = self.get_normal_information(self.logic_mesh)
        self.isconvex = self.is_convex()
        if self.isconvex == False:
            if sort_BdNode_idx is None:
                raise ValueError('The boundary is not convex, you must give the sort_BdNode')
        self.roll_SortBdNode()

    def get_logic_mesh(self) :
        if self.TD == 2:
            if self.is_convex():
                logic_mesh = TriangleMesh(self.node.copy(),self.cell) # 更新
            else:
                logic_node = self.get_logic_node()
                logic_cell = self.cell
                logic_mesh = TriangleMesh(logic_node,logic_cell)
            return logic_mesh
        elif self.TD == 3:
            if not self.is_convex():
                raise ValueError('非凸多面体无法构建逻辑网格')
            else:
                logic_mesh = TetrahedronMesh(self.node.copy(),self.cell)
            return logic_mesh
        
    def is_convex(self):
        """
        @brief is_convex : 判断边界是否是凸的
        """
        from scipy.spatial import ConvexHull
        intnode = self.node[self.Vertex_idx]
        hull = ConvexHull(intnode)
        return len(intnode) == len(hull.vertices)
    
    def node_to_face(self): # 作为三维网格的辅助函数
        mesh = self.mesh
        NN = mesh.number_of_nodes()
        NF = mesh.number_of_faces()

        face = mesh.entity('face')
        NVF = 3
        node2face = csr_matrix(
                (
                    bm.ones(NVF*NF, dtype=bm.bool),
                    (
                        face.flat,
                        bm.repeat(range(NF), NVF)
                    )
                ), shape=(NN, NF))
        return node2face
    
    def get_normal_information(self,mesh:Union[TriangleMesh,TetrahedronMesh]):
        """
        @brief get_normal_information: 获取边界点法向量
        """
        Bdinnernode_idx = self.Bdinnernode_idx
        BdFaceidx = self.BdFaceidx
        if self.TD == 3:
            Arrisnode_idx = self.Arrisnode_idx
            node2face = self.node_to_face()
            Ar_node2face = node2face[Arrisnode_idx][:,BdFaceidx]
            i0 , j0 = bm.nonzero(Ar_node2face)
            bdfun0 = mesh.face_unit_normal(index=BdFaceidx[j0])
            normal0,inverse0 = bm.unique(bdfun0,return_inverse=True ,axis = 0)
            _,index0,counts0 = bm.unique(i0,return_index=True,return_counts=True)   
            maxcount = bm.max(counts0)
            mincount = bm.min(counts0)
            Ar_node2normal_idx = -bm.ones((len(Arrisnode_idx),maxcount),dtype=bm.int32)
            Ar_node2normal_idx = bm.set_at(Ar_node2normal_idx,
                                            (slice(None),slice(mincount)),
                                            inverse0[index0[:,None]+bm.arange(mincount)])
            for i in range(maxcount-mincount):
                isaimnode = counts0 > mincount+i
                Ar_node2normal_idx = bm.set_at(Ar_node2normal_idx,(isaimnode,mincount+i) , 
                                                inverse0[index0[isaimnode]+mincount+i])
            Ar_node2normal_idx = bm.apply_along_axis(lambda x: bm.unique(x[x>=0])
                                                    ,axis=1,arr=Ar_node2normal_idx)
            Ar_node2normal = normal0[Ar_node2normal_idx]
        elif self.TD == 2:
            node2face = self.node2edge
        
        Bi_node2face = node2face[Bdinnernode_idx][:,BdFaceidx]
        i1 , j1 = bm.nonzero(Bi_node2face)
        bdfun1 = mesh.face_unit_normal(index=BdFaceidx[j1])
        _,index1 = bm.unique(i1,return_index=True)
        Bi_node_normal = bdfun1[index1]
        if self.TD == 2:
            return Bi_node_normal
        else:
            return Bi_node_normal, Ar_node2normal
    
    def roll_SortBdNode(self):
        """
        对齐边界点与角点
        """
        sBdnodeidx = self.sort_BdNode_idx
        Vertexidx = self.Vertex_idx
        if sBdnodeidx is not None and sBdnodeidx[0] != Vertexidx[0]:
            K = bm.where(sBdnodeidx[:,None] == Vertexidx)[0][0]
            self.sort_BdNode_idx = bm.roll(sBdnodeidx,-K)
        
    def get_boundary_condition(self,p) -> TensorLike:
        """
        逻辑网格的边界条件
        """
        node = self.node
        sBdNodeidx = self.sort_BdNode_idx 
        Vertexidx = self.Vertex_idx

        physics_domain = node[Vertexidx]
        num_sides = physics_domain.shape[0]
        angles = bm.linspace(0,2*bm.pi,num_sides,endpoint=False)
        logic_domain = bm.stack([bm.cos(angles),bm.sin(angles)],axis=1)
        logic_bdnode = bm.zeros_like(node,dtype=bm.float64)
        
        Pside_vector = bm.roll(physics_domain,-1,axis=0) - physics_domain
        Lside_vector = bm.roll(logic_domain,-1,axis=0) - logic_domain
        Pside_length = bm.linalg.norm(Pside_vector,axis=1)
        Lside_length = bm.linalg.norm(Lside_vector,axis=1)
        rate = Lside_length / Pside_length
        theta = bm.arctan2(Lside_vector[:,1],Lside_vector[:,0]) -\
                bm.arctan2(Pside_vector[:,1],Pside_vector[:,0]) 
        A = rate[:,None,None] * (bm.array([[bm.cos(theta),bm.sin(theta)],
                                           [-bm.sin(theta),bm.cos(theta)]],dtype=bm.float64)).T

        K = bm.where(sBdNodeidx[:,None] == Vertexidx)[0]
        K = bm.concatenate([K,[len(sBdNodeidx)]])

        A_repeat = bm.repeat(A,K[1:]-K[:-1],axis=0)
        PVertex_repeat = bm.repeat(physics_domain,K[1:]-K[:-1],axis=0)
        LVertex_repeat = bm.repeat(logic_domain,K[1:]-K[:-1],axis=0)
        Aim_vector = (A_repeat@((node[sBdNodeidx]-PVertex_repeat)[:,:,None])).reshape(-1,2)
        logic_bdnode = bm.set_at(logic_bdnode,sBdNodeidx,Aim_vector+LVertex_repeat)

        map = bm.where((node[:,None] == p).all(axis=2))[0]
        return logic_bdnode[map]
    
    def get_logic_node(self) -> TensorLike:
        """
        logic_node : 逻辑网格的节点坐标
        """
        mesh = self.mesh
        bdc = self.get_boundary_condition
        p = 1 # 有限元空间次数
        space = LagrangeFESpace(mesh, p=p)
        bform = BilinearForm(space)
        bform.add_integrator(ScalarDiffusionIntegrator(q=p+1))
        A = bform.assembly()
        lform = LinearForm(space)
        lform.add_integrator(ScalarSourceIntegrator(source=0,q=p+1))
        F = lform.assembly()
        bc0 = DirichletBC(space = space, gd = lambda p : bdc(p)[:,0])
        bc1 = DirichletBC(space = space, gd = lambda p : bdc(p)[:,1])
        uh0 = space.function()
        uh1 = space.function()
        A1, F1 = bc0.apply(A, F, uh0)
        A2, F2 = bc1.apply(A, F, uh1)
        uh0 = bm.set_at(uh0 , slice(None), spsolve(A1, F1 , solver="scipy"))
        uh1 = bm.set_at(uh1 , slice(None), spsolve(A2, F2 , solver="scipy"))
        logic_node = bm.stack([uh0,uh1],axis=1)
        return logic_node

class Harmap_MMPDE(LogicMesh):
    def __init__(self, 
                 mesh:Union[TriangleMesh,TetrahedronMesh] , 
                 uh:TensorLike,
                 pde ,
                 beta :float ,
                 Vertex_idx : TensorLike,
                 Bdinnernode_idx : TensorLike,
                 Arrisnode_idx : Optional[TensorLike] = None,
                 sort_BdNode_idx : Optional[TensorLike] = None,
                 alpha = 0.5, 
                 mol_times = 1 , 
                 redistribute = True) -> None:
        """
        mesh : 初始物理网格
        uh : 物理网格上的解
        pde : 微分方程基本信息
        beta : 控制函数的参数
        alpha : 移动步长控制参数
        mol_times : 磨光次数
        redistribute : 是否预处理边界节点
        """
        super().__init__(mesh = mesh,
                         Vertex_idx = Vertex_idx,
                         Bdinnernode_idx = Bdinnernode_idx,
                         Arrisnode_idx = Arrisnode_idx,
                         sort_BdNode_idx = sort_BdNode_idx)
        self.uh = uh
        self.pde = pde
        self.beta = beta
        self.alpha = alpha
        self.mol_times = mol_times
        self.NN = mesh.number_of_nodes()
        self.BDNN = len(self.BdNodeidx)

        self.cm = mesh.entity_measure('cell')
        # 新网格下没有该方法
        if self.TD == 2:
            self.node2cell = TM(self.node, self.cell).ds.node_to_cell()
        elif self.TD == 3:
            self.node2cell = THM(self.node, self.cell).ds.node_to_cell()
        self.isBdNode = mesh.boundary_node_flag()
        self.redistribute = redistribute

        self.W = bm.array([[0,1],[-1,0]],dtype=bm.int32)
        self.localEdge = bm.array([[1,2],[2,0],[0,1]],dtype=bm.int32)

        self.star_measure,self.i,self.j = self.get_star_measure()
        self.G = self.get_control_function(self.beta , self.mol_times)
        self.A , self.b = self.get_linear_constraint()
        if redistribute and sort_BdNode_idx is None:
            raise ValueError('redistributing boundary , you must give the sort_BdNode')

    def get_star_measure(self)->TensorLike:
        """
        计算每个节点的星的测度
        """
        star_measure = bm.zeros(self.NN,dtype=bm.float64)
        i,j = bm.nonzero(self.node2cell)
        bm.add_at(star_measure , i , self.cm[j])
        return star_measure,i,j
    
    def get_control_function(self,beta:float,mol_times:int):
        """
        @brief 计算控制函数
        @param beta: float 控制函数的参数
        @param mol_times: int 磨光次数
        """
        cell = self.cell

        cm = self.cm
        gphi = self.mesh.grad_lambda()
        guh_incell = bm.sum(self.uh[cell,None] * gphi,axis=1)
        max_norm_guh = bm.max(bm.linalg.norm(guh_incell,axis=1))
        M_incell = bm.sqrt(1 +beta *bm.sum( guh_incell**2,axis=1)/max_norm_guh)
        M = bm.zeros(self.NN,dtype=bm.float64)
        bm.add_at(M , self.i , (cm *M_incell)[self.j])
        M /= self.star_measure
        if mol_times > 0:
            for k in range(mol_times):
                M = bm.zeros(self.NN,dtype=bm.float64)
                bm.add_at(M , self.i , (cm *M_incell)[self.j])
                M /= self.star_measure
                M_incell = bm.mean(M[cell],axis=1)
        return 1/M_incell
    
    def get_stiff_matrix(self,mesh:Union[TriangleMesh,TetrahedronMesh],G:TensorLike):
        """
        @brief 组装刚度矩阵
        @param mesh: 物理网格
        @param G: 控制函数
        """
        q = 3
        cm = mesh.entity_measure('cell')
        qf = mesh.quadrature_formula(q)
        bcs, ws = qf.get_quadrature_points_and_weights()
        space = LagrangeFESpace(mesh, p=1)
        gphi = space.grad_basis(bcs)

        cell2dof = space.cell_to_dof()
        GDOF = space.number_of_global_dofs()
        
        H = bm.einsum('q , cqid , c ,cqjd, c -> cij ',ws, gphi ,G , gphi, cm)
        I = bm.broadcast_to(cell2dof[:, :, None], shape=H.shape)
        J = bm.broadcast_to(cell2dof[:, None, :], shape=H.shape)
        H = csr_matrix((H.flat, (I.flat, J.flat)), shape=(GDOF, GDOF))
        return H
    
    def get_linear_constraint(self):
        """
        @brief 组装线性约束
        """
        logic_node = self.logic_node
        NN = self.NN
        BDNN = self.BDNN
        BdNodeidx = self.BdNodeidx
        Vertex_idx = self.Vertex_idx
        Bdinnernode_idx = self.Bdinnernode_idx
        Binnorm = self.Bi_Lnode_normal
        logic_Bdinnode = logic_node[Bdinnernode_idx]
        logic_Vertex = logic_node[Vertex_idx]
        if self.TD == 2:
            b = bm.zeros(NN,dtype=bm.float64)
            b_val0 = bm.sum(logic_Bdinnode*Binnorm,axis=1)
            b_val1 = logic_Vertex[:,0]
            b_val2 = logic_Vertex[:,1]
            b = bm.set_at(b , Bdinnernode_idx , b_val0)
            b = bm.set_at(b , Vertex_idx , b_val1)[BdNodeidx]
            b = bm.concatenate([b,b_val2])
  
            A1_diag = bm.zeros(NN  , dtype=bm.float64)
            A2_diag = bm.zeros(NN  , dtype=bm.float64)
            A1_diag = bm.set_at(A1_diag , Bdinnernode_idx , Binnorm[:,0])
            A2_diag = bm.set_at(A2_diag , Bdinnernode_idx , Binnorm[:,1])
            A1_diag = bm.set_at(A1_diag , Vertex_idx , 1)[BdNodeidx]
            A2_diag = bm.set_at(A2_diag , Vertex_idx , 0)[BdNodeidx]
            A1 = spdiags(A1_diag,0,BDNN,BDNN , format='csr')
            A2 = spdiags(A2_diag,0,BDNN,BDNN , format='csr')
            VNN = len(Vertex_idx)
            Vbd_constraint1 = csr_matrix((VNN, BDNN), dtype=bm.float64)
            data = bm.ones(VNN,dtype=bm.float64)
            Vbd_constraint2 = csr_matrix((data, (bm.arange(VNN), Vertex_idx)), shape=(VNN, NN))
            A = bmat([[A1,A2],[Vbd_constraint1,Vbd_constraint2[:,BdNodeidx]]],format='csr')

        elif self.TD == 3:
            Arrisnode_idx = self.Arrisnode_idx
            Arnnorm = self.Ar_Lnode_normal
            logic_Arnode = logic_node[Arrisnode_idx]
            ArNN = len(Arrisnode_idx)
            VNN = len(Vertex_idx)

            b = bm.zeros(NN,dtype=bm.float64)
            b_val0 = bm.sum(logic_Bdinnode*Binnorm,axis=1)
            b_val1 = bm.sum(logic_Arnode*Arnnorm[:,0,:],axis=1)
            b_val2 = bm.sum(logic_Arnode*Arnnorm[:,1,:],axis=1)
            b_val3 = logic_Vertex[:,0]
            b_val4 = logic_Vertex[:,1]
            b_val5 = logic_Vertex[:,2]
            bm.add_at(b_val2 , slice(VNN) , b_val4) 
            b = bm.set_at(b , Bdinnernode_idx , b_val0)
            b = bm.set_at(b , Arrisnode_idx , b_val1)
            b = bm.set_at(b , Vertex_idx , b_val3)
            b = bm.concatenate([b,b_val2,b_val5])

            index0 = NN * bm.arange(self.TD) + Bdinnernode_idx[:,None]
            index1 = NN * bm.arange(self.TD) + Arrisnode_idx[:,None]
            index2 = NN * bm.arange(self.TD) + BdNodeidx[:,None]

            A_diag = bm.zeros(self.TD * NN  , dtype=bm.float64)
            A_diag = bm.set_at(A_diag , index0 , Binnorm)
            A_diag = bm.set_at(A_diag , index1 , Arnnorm[:,0,:])
            A_diag = bm.set_at(A_diag , Vertex_idx , 1)

            A1 = spdiags(A_diag[:NN][BdNodeidx],0, BDNN ,BDNN , format='csr')
            A2 = spdiags(A_diag[NN:2*NN][BdNodeidx],0, BDNN ,BDNN , format='csr')
            A3 = spdiags(A_diag[2*NN:][BdNodeidx],0, BDNN ,BDNN , format='csr')

            rol_Ar = bm.repeat(bm.arange(ArNN)[None,:],3,axis=0).flat
            rol_Ar = bm.concatenate([rol_Ar,bm.arange(VNN)])
            cow_Ar = bm.concatenate([index1.T.flat,Vertex_idx+NN])
            data_Ar = bm.concatenate([Arnnorm[:,1,:].T.flat,bm.ones(VNN,bm.float64)])
            Ar_constraint = csr_matrix((data_Ar,(rol_Ar, cow_Ar)),shape=(ArNN,3*NN))
            Vertex_constraint = csr_matrix((bm.ones(VNN,dtype=bm.float64),
                                (bm.arange(VNN),Vertex_idx + 2 * NN)),shape=(VNN,3*NN))

            Ar_constraint = Ar_constraint[:, (index2.T).flat]
            Vertex_constraint = Vertex_constraint[:, (index2.T).flat]
            A_part = bmat([[A1,A2,A3]],format='csr')
            A = bmat([[A_part],[Ar_constraint],[Vertex_constraint]],format='csr')
        return A,b

    def solve_move_LogicNode(self):
        """
        @brief 交替求解逻辑网格点
        process_logic_node : 新逻辑网格点
        move_vector_field : 逻辑网格点移动向量场
        """
        from scipy.sparse.linalg import spsolve
        isBdNode = self.isBdNode
        H = self.get_stiff_matrix(self.mesh , self.G)
        H11 = H[~self.isBdNode][:, ~self.isBdNode]
        H12 = H[~self.isBdNode][:, self.isBdNode]
        H21 = H[self.isBdNode][:, ~self.isBdNode]
        H22 = H[self.isBdNode][:, self.isBdNode]

        A,b= self.A,self.b
        # 获得一个初始逻辑网格点的拷贝
        init_logic_node = self.logic_node.copy()
        process_logic_node = self.logic_node.copy()
        if self.redistribute:
            process_logic_node = self.redistribute_boundary()
        # 移动逻辑网格点
        f1 = -H12@process_logic_node[isBdNode,0]
        f2 = -H12@process_logic_node[isBdNode,1]

        move_innerlogic_node_x = spsolve1(H11, f1 )
        move_innerlogic_node_y = spsolve1(H11, f2 )
        process_logic_node = bm.set_at(process_logic_node , ~isBdNode, 
                                bm.stack([move_innerlogic_node_x,
                                          move_innerlogic_node_y],axis=1))
        
        f1 = -H21@move_innerlogic_node_x
        f2 = -H21@move_innerlogic_node_y
        b0 = bm.concatenate((f1,f2,b),axis=0)

        A1 = block_diag((H22, H22),format='csr')
        zero_matrix = csr_matrix((A.shape[0],A.shape[0]),dtype=bm.float64)
        A0 = bmat([[A1,A.T],[A,zero_matrix]],format='csr')

        move_bdlogic_node = spsolve(A0,b0)[:2*H22.shape[0]]
        process_logic_node = bm.set_at(process_logic_node , isBdNode,
                                bm.stack((move_bdlogic_node[:H22.shape[0]],
                                        move_bdlogic_node[H22.shape[0]:]),axis=1))
        
        move_vector_field = init_logic_node - process_logic_node
        return process_logic_node,move_vector_field

    def get_physical_node(self,move_vertor_field,logic_node_move):
        """
        @brief 计算物理网格点
        @param move_vertor_field: 逻辑网格点移动向量场
        @param logic_node_move: 移动后的逻辑网格点
        """
        node = self.node
        cell = self.cell
        cm = self.cm

        A = (node[cell[:,1:]] - node[cell[:,0,None]]).transpose(0,2,1)
        B = (logic_node_move[cell[:,1:]] - logic_node_move[cell[:,0,None]]).transpose(0,2,1)
        grad_x_incell = (A@bm.linalg.inv(B)) * cm[:,None,None]

        grad_x = bm.zeros((self.NN,2,2),dtype=bm.float64)
        bm.add_at(grad_x , self.i , grad_x_incell[self.j])
        grad_x /= self.star_measure[:,None,None]

        delta_x = (grad_x @ move_vertor_field[:,:,None]).reshape(-1,2)

        Bin_tangent = self.Bi_Pnode_normal @ self.W
        Bdinnernode_idx = self.Bdinnernode_idx
        dot = bm.sum(Bin_tangent * delta_x[Bdinnernode_idx],axis=1)
        delta_x = bm.set_at(delta_x,Bdinnernode_idx,dot[:,None] * Bin_tangent)

        # 物理网格点移动距离
        C = (delta_x[cell[:,1:]] - delta_x[cell[:,0,None]]).transpose(0,2,1)
        a = C[:,0,0]*C[:,1,1] - C[:,0,1]*C[:,1,0]
        b = A[:,0,0]*C[:,1,1] - A[:,0,1]*C[:,1,0] + C[:,0,0]*A[:,1,1] - C[:,0,1]*A[:,1,0]
        c = A[:,0,0]*A[:,1,1] - A[:,0,1]*A[:,1,0]
        discriminant = b**2 - 4*a*c
        discriminant = bm.where(discriminant > 0, discriminant, 0)
        x1 = (-b + bm.sqrt(discriminant))/(2*a)
        x2 = (-b - bm.sqrt(discriminant))/(2*a)
        positive_x1 = bm.where(x1 > 0, x1, bm.inf)
        positive_x2 = bm.where(x2 > 0, x2, bm.inf)
        eta = bm.min([bm.min(positive_x1),bm.min(positive_x2),1])
        node = node + self.alpha * eta * delta_x

        return node
            
    
    def redistribute_boundary(self):
        """
        @brief 预处理边界节点
        """
        node = self.node
        logic_node = self.logic_node.copy()
        Vertex_idx = self.Vertex_idx
        sort_Bdnode_idx = self.sort_BdNode_idx
        K = bm.where(sort_Bdnode_idx[:,None] == Vertex_idx)[0]
        isBdedge = self.mesh.boundary_face_flag()
        node2edge = TM(self.node, self.cell).ds.node_to_edge()
        edge2cell = self.mesh.face_to_cell()
        G_cell = self.get_control_function(self.beta,mol_times=4)[0]
        
        VNN = len(Vertex_idx)
        for n in range(VNN):
            side_node_idx = sort_Bdnode_idx[K[n]:K[n+1]+1] \
                            if n < VNN - 1 else sort_Bdnode_idx[K[n]:]
            side_node2edge = node2edge[side_node_idx[1:-1]][:,isBdedge]
            i,j = bm.nonzero(side_node2edge)
            _,k = bm.unique(j,return_index=True)
            j = j[bm.sort(k)]
            side_cell_idx = edge2cell[isBdedge][j][:,0]
            side_G = G_cell[side_cell_idx]

            SNN = side_node_idx.shape[0]
            side_node = node[side_node_idx]
            side_length = bm.linalg.norm(side_node[-1] - side_node[0])
            logic_side_node = logic_node[side_node_idx]

            direction = logic_side_node[-1] - logic_side_node[0]
            angle = bm.arctan2(direction[1],direction[0])
            rotate = bm.array([[bm.cos(-angle),-bm.sin(-angle)],
                            [bm.sin(-angle),bm.cos(-angle)]])
            rate =bm.linalg.norm(direction)/side_length

            x = bm.linalg.norm(side_node - side_node[0],axis=1)
            cell = bm.stack([bm.arange(SNN-1),bm.arange(1,SNN)],axis=1)
            side_mesh = IntervalMesh(x , cell)
            H = self.get_stiff_matrix(side_mesh,side_G)
            F = bm.zeros(SNN , dtype= bm.float64)
            F = bm.set_at(F , [0,-1] , [x[0],x[-1]])
            bdIdx = bm.zeros(SNN , dtype= bm.float64)
            bdIdx = bm.set_at(bdIdx , [0,-1] , 1)
            D0 = spdiags(1-bdIdx ,0, SNN, SNN)
            D1 = spdiags(bdIdx , 0 , SNN, SNN)
            H = D0@H + D1
            x = spsolve1(H,F)
            logic_side_node = logic_side_node[0] + rate * \
                                bm.stack([x,bm.zeros_like(x)],axis=1) @ rotate
            logic_node = bm.set_at(logic_node , side_node_idx[1:-1] , logic_side_node[1:-1])
        return logic_node

    def interpolate(self,move_node):
        """
        @brief 将解插值到新网格上
        @param move_node: 移动后的物理节点
        """
        from scipy.sparse.linalg import spsolve
        delta_x = self.node - move_node
        mesh0 = TriangleMesh(self.node,self.cell)
        space = LagrangeFESpace(mesh0, p=1)
        cell2dof = space.cell_to_dof()
        qf = mesh0.quadrature_formula(3,'cell')
        bcs, ws = qf.get_quadrature_points_and_weights()
        cm = mesh0.entity_measure('cell')
        phi = space.basis(bcs)
        M = bm.einsum('q , cqi ,cqj, c -> cij ',ws, phi ,phi , cm)   
        gphi = space.grad_basis(bcs)
        P = bm.einsum('q , cqid , cid ,cqj ,c -> cij' , ws , gphi,  delta_x[cell2dof], phi, cm)
        GDOF = space.number_of_global_dofs()
        I = bm.broadcast_to(space.cell_to_dof()[:, :, None], shape=P.shape)
        J = bm.broadcast_to(space.cell_to_dof()[:, None, :], shape=P.shape)
        M = csr_matrix((M.flat, (I.flat, J.flat)), shape=(GDOF, GDOF))
        P = csr_matrix((P.flat, (I.flat, J.flat)), shape=(GDOF, GDOF))
        def ODEs(t,y):
            f = spsolve(M,P@y)
            return f
        # 初值条件  
        uh0 = self.uh
        # 范围
        tau_span = [0,1]
        # 求解
        sol = solve_ivp(ODEs,tau_span,uh0,method='RK23').y[:,-1]
        return sol
    
    def construct(self,new_mesh):
        """
        @brief construct: 重构信息
        @param new_mesh:新的网格
        """
        self.mesh = new_mesh
        # node 更新之前完成插值
        self.uh = self.interpolate(new_mesh.entity('node'))
        self.node = new_mesh.entity('node')
        self.cm = new_mesh.entity_measure('cell')
        self.star_measure = self.get_star_measure()[0]
        self.G = self.get_control_function(self.beta , self.mol_times)


    def mesh_redistribution(self ,uh, tol = None , maxit = 1000):
        """
        @brief mesh_redistribution: 网格重构算法
        @param tol: 容许误差
        @param maxit 最大迭代次数
        """
        self.uh = uh
         # 计算容许误差
        em = self.logic_mesh.entity_measure('edge')
        if tol is None:
            tol = bm.min(em)* 0.1
            print(f'容许误差为{tol}')

        for i in range(maxit):
            logic_node,vector_field = self.solve_move_LogicNode()
            L_infty_error = bm.max(bm.linalg.norm(self.logic_node - logic_node,axis=1))
            node = self.get_physical_node(vector_field,logic_node)
            mesh0 = TriangleMesh(node,self.cell)
            print(f'第{i+1}次迭代的差值为{L_infty_error}')
            self.construct(mesh0)
            if L_infty_error < tol:
                print(f'迭代总次数:{i+1}次')
                return mesh0 , self.uh
            elif i == maxit - 1:
                print('超出最大迭代次数')
                break




class Mesh_Data_Harmap():
    def __init__(self,mesh:Union[TriangleMesh,TetrahedronMesh],Vertex ) -> None:
        self.mesh = mesh
        self.node = mesh.entity('node')
        self.isBdNode = mesh.boundary_node_flag()
        self.Vertex = Vertex
        self.isconvex = self.is_convex()
        
    def is_convex(self):
        """
        判断边界是否是凸的
        """
        from scipy.spatial import ConvexHull
        Vertex = self.Vertex
        hull = ConvexHull(Vertex)
        return len(Vertex) == len(hull.vertices)
    
    def sort_bdnode_and_bdface(self) -> TensorLike:
        mesh = self.mesh
        BdNodeidx = mesh.boundary_node_index()
        BdEdgeidx = mesh.boundary_face_index()
        node = mesh.node
        edge = mesh.edge
        cell = mesh.cell
        # 对边界边和点进行排序
        mesh_0 = TM(node,cell)
        node2edge = mesh_0.ds.node_to_face()
        bdnode2edge = node2edge[BdNodeidx][:,BdEdgeidx]
        i,j = bm.nonzero(bdnode2edge)
        bdnode2edge = j.reshape(-1,2)
        glob_bdnode2edge = bm.zeros_like(node,dtype=bm.int32)
        glob_bdnode2edge = bm.set_at(glob_bdnode2edge,BdNodeidx,BdEdgeidx[bdnode2edge])
        
        sort_glob_bdedge_idx_list = []
        sort_glob_bdnode_idx_list = []

        start_bdnode_idx = BdNodeidx[0]
        sort_glob_bdnode_idx_list.append(start_bdnode_idx)
        current_node_idx = start_bdnode_idx
        
        for i in range(bdnode2edge.shape[0]):
            if edge[glob_bdnode2edge[current_node_idx,0],1] == current_node_idx:
                next_edge_idx = glob_bdnode2edge[current_node_idx,1]
            else:
                next_edge_idx = glob_bdnode2edge[current_node_idx,0]
            sort_glob_bdedge_idx_list.append(next_edge_idx)
            next_node_idx = edge[next_edge_idx,1]
            # 处理空洞区域
            if next_node_idx == start_bdnode_idx:
                if i < bdnode2edge.shape[0] - 1:
                    remian_bdnode_idx = list(set(BdNodeidx)-set(sort_glob_bdnode_idx_list))
                    start_bdnode_idx = remian_bdnode_idx[0]
                    next_node_idx = start_bdnode_idx
                else:
                # 闭环跳出循环
                    break
            sort_glob_bdnode_idx_list.append(next_node_idx)
            current_node_idx = next_node_idx
        return bm.array(sort_glob_bdnode_idx_list,dtype=bm.int32),\
                bm.array(sort_glob_bdedge_idx_list,dtype=bm.int32)
    
    def get_normal_inform(self,sort_BdNode_idx = None) -> None:
        from scipy.sparse import csr_matrix
        mesh = self.mesh
        BdNodeidx = mesh.boundary_node_index()
        if sort_BdNode_idx is not None:
            BdNodeidx = sort_BdNode_idx
        BdFaceidx = mesh.boundary_face_index()
        TD = mesh.top_dimension()
        node = mesh.entity('node')
        cell = mesh.entity('cell')
        if TD == 2:
            mesh = TM(node,cell)
            node2face = mesh.ds.node_to_face()
        elif TD == 3:
            def node_to_face(mesh): # 作为三维网格的辅助函数
                NN = mesh.number_of_nodes()
                NF = mesh.number_of_faces()
                face = mesh.entity('face')
                NVF = 3
                node2face = csr_matrix(
                        (
                            bm.ones(NVF*NF, dtype=bm.bool),
                            (
                                face.flat,
                                bm.repeat(range(NF), NVF)
                            )
                        ), shape=(NN, NF))
                return node2face
            node2face = node_to_face(mesh)
        bd_node2face = node2face[BdNodeidx][:,BdFaceidx]
        i , j = bm.nonzero(bd_node2face)

        bdfun = mesh.face_unit_normal(index=BdFaceidx[j])
        normal,inverse = bm.unique(bdfun,return_inverse=True ,axis = 0)
        
        _,index,counts = bm.unique(i,return_index=True,return_counts=True)
        cow = bm.max(counts)
        r = bm.min(counts)

        node2face_normal = -bm.ones((BdNodeidx.shape[0],cow),dtype=bm.int32)
        node2face_normal = bm.set_at(node2face_normal,(slice(None),slice(r)),inverse[index[:,None]+bm.arange(r)])
        for i in range(cow-r):
            isaimnode = counts > r+i
            node2face_normal = bm.set_at(node2face_normal,(isaimnode,r+i) , 
                                            inverse[index[isaimnode]+r+i])
        node2face_normal = bm.apply_along_axis(lambda x: bm.set_at(
                                                - bm.ones(TD , dtype = bm.int32)
                                                , slice(len(bm.unique(x[x>=0])))
                                                ,bm.unique(x[x>=0]))
                                                ,axis=1, arr=node2face_normal)
        return node2face_normal,normal
    
    def get_basic_infom(self):
        mesh = self.mesh
        node2face_normal,normal = self.get_normal_inform()
        BdNodeidx = mesh.boundary_node_index()
        Bdinnernode_idx = BdNodeidx[node2face_normal[:,1] < 0]
        is_convex = self.isconvex
        if is_convex:
            Vertex_idx = BdNodeidx[node2face_normal[:,-1] >= 0]
            if mesh.TD == 3:
                Arrisnode_idx = BdNodeidx[(node2face_normal[:,1] >= 0) & (node2face_normal[:,-1] < 0)]
                return Vertex_idx,Bdinnernode_idx,Arrisnode_idx
            return Vertex_idx,Bdinnernode_idx
        else:
            if self.Vertex is None:
                raise ValueError('The boundary is not convex, you must give the Vertex')
            minus = mesh.node - self.Vertex[:,None]
            judge_vertex = bm.sum(((minus**2)[:,:,0],(minus**2)[:,:,1]),axis=0) < 1e-10
            K = bm.arange(mesh.number_of_nodes())
            Vertex_idx = judge_vertex @ K
            sort_Bdnode_idx,sort_Bdface_idx = self.sort_bdnode_and_bdface()
            return Vertex_idx,Bdinnernode_idx,sort_Bdnode_idx